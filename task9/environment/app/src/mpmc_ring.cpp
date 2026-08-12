#include "mpmc_ring.h"

#include <atomic>
#include <cstdint>
#include <memory>
#include <stdexcept>
#include <thread>
#include <utility>
#include <vector>

namespace dynamo {

class MpmcRing::Impl {
public:
    Impl(
        std::size_t capacity,
        Ticket initial_ticket,
        ObservationHook hook
    )
        : capacity_(capacity),
          mask_(capacity - 1),
          values_(nullptr),
          reserve_ticket_(initial_ticket),
          publish_ticket_(initial_ticket),
          consume_ticket_(initial_ticket),
          hook_(std::move(hook)) {
        if (
            capacity_ < 2
            || (
                capacity_
                & (capacity_ - 1)
            ) != 0
        ) {
            throw std::invalid_argument(
                "capacity must be a power of two and at least 2"
            );
        }

        values_ = std::make_unique<Value[]>(
            capacity_
        );
    }

    bool try_push(
        Value value
    ) {
        return try_push_batch(
            std::vector<Value>{value}
        );
    }

    bool try_push_batch(
        const std::vector<Value>& values
    ) {
        validate_batch_size(
            values.size()
        );

        if (
            closed_.load(
                std::memory_order_acquire
            )
        ) {
            return false;
        }

        Ticket first =
            reserve_ticket_.load(
                std::memory_order_acquire
            );

        if (
            !producer_range_available(
                first,
                values.size()
            )
        ) {
            return false;
        }

        invoke_hook(
            HookPoint::producer_candidate,
            first,
            values.size()
        );

        if (
            closed_.load(
                std::memory_order_acquire
            )
        ) {
            return false;
        }

        const Ticket desired =
            first
            + static_cast<Ticket>(
                values.size()
            );

        /*
         * The candidate range was eligible when it was
         * observed, so claiming it is a single exchange.
         */
        if (
            !reserve_ticket_
                .compare_exchange_strong(
                    first,
                    desired,
                    std::memory_order_acq_rel,
                    std::memory_order_acquire
                )
        ) {
            return false;
        }

        invoke_hook(
            HookPoint::producer_reserved,
            first,
            values.size()
        );

        if (
            closed_.load(
                std::memory_order_acquire
            )
        ) {
            return false;
        }

        for (
            std::size_t offset = 0;
            offset < values.size();
            ++offset
        ) {
            values_[
                slot_index(
                    first
                    + static_cast<Ticket>(
                        offset
                    )
                )
            ] = values[offset];
        }

        /*
         * Publication is ordered by logical ticket, so a
         * consumer never sees a hole: this range becomes
         * visible only once every earlier range has been
         * published.
         */
        while (
            publish_ticket_.load(
                std::memory_order_acquire
            ) != first
        ) {
            std::this_thread::yield();
        }

        publish_ticket_.store(
            desired,
            std::memory_order_release
        );

        invoke_hook(
            HookPoint::producer_published,
            first,
            values.size()
        );

        return true;
    }

    std::optional<Value>
    try_pop() {
        auto batch =
            try_pop_batch(1);

        if (!batch) {
            return std::nullopt;
        }

        return (*batch)[0];
    }

    std::optional<
        std::vector<Value>
    >
    try_pop_batch(
        std::size_t count
    ) {
        validate_batch_size(count);

        Ticket first =
            consume_ticket_.load(
                std::memory_order_acquire
            );

        if (
            !consumer_range_available(
                first,
                count
            )
        ) {
            return std::nullopt;
        }

        invoke_hook(
            HookPoint::consumer_candidate,
            first,
            count
        );

        const Ticket desired =
            first
            + static_cast<Ticket>(
                count
            );

        if (
            !consume_ticket_
                .compare_exchange_strong(
                    first,
                    desired,
                    std::memory_order_acq_rel,
                    std::memory_order_acquire
                )
        ) {
            return std::nullopt;
        }

        invoke_hook(
            HookPoint::consumer_reserved,
            first,
            count
        );

        std::vector<Value> values;
        values.reserve(count);

        for (
            std::size_t offset = 0;
            offset < count;
            ++offset
        ) {
            values.push_back(
                values_[
                    slot_index(
                        first
                        + static_cast<Ticket>(
                            offset
                        )
                    )
                ]
            );
        }

        invoke_hook(
            HookPoint::consumer_released,
            first,
            count
        );

        return values;
    }

    void close() {
        closed_.store(
            true,
            std::memory_order_release
        );
    }

    bool closed() const noexcept {
        return closed_.load(
            std::memory_order_acquire
        );
    }

    std::size_t
    capacity() const noexcept {
        return capacity_;
    }

private:
    void validate_batch_size(
        std::size_t count
    ) const {
        if (
            count == 0
            || count > capacity_
        ) {
            throw std::invalid_argument(
                "batch size must be between 1 and capacity"
            );
        }
    }

    std::size_t slot_index(
        Ticket ticket
    ) const noexcept {
        return static_cast<std::size_t>(
            ticket
            & static_cast<Ticket>(
                mask_
            )
        );
    }

    /*
     * A range may be reserved while the ring holds fewer
     * than capacity_ logical values that the consumers
     * have not taken yet.
     */
    bool producer_range_available(
        Ticket first,
        std::size_t count
    ) const {
        const Ticket consumed =
            consume_ticket_.load(
                std::memory_order_acquire
            );

        const Ticket outstanding =
            first
            + static_cast<Ticket>(
                count
            )
            - consumed;

        return outstanding
            <= static_cast<Ticket>(
                capacity_
            );
    }

    bool consumer_range_available(
        Ticket first,
        std::size_t count
    ) const {
        const Ticket published =
            publish_ticket_.load(
                std::memory_order_acquire
            );

        return first
            + static_cast<Ticket>(
                count
            )
            <= published;
    }

    void invoke_hook(
        HookPoint point,
        Ticket first_ticket,
        std::size_t count
    ) {
        if (!hook_) {
            return;
        }

        hook_(
            point,
            first_ticket,
            count
        );
    }

    const std::size_t capacity_;
    const std::size_t mask_;

    std::unique_ptr<Value[]> values_;

    std::atomic<Ticket> reserve_ticket_;
    std::atomic<Ticket> publish_ticket_;
    std::atomic<Ticket> consume_ticket_;

    std::atomic<bool> closed_{false};

    ObservationHook hook_;
};

MpmcRing::MpmcRing(
    std::size_t capacity,
    Ticket initial_ticket,
    ObservationHook hook
)
    : impl_(
          std::make_unique<Impl>(
              capacity,
              initial_ticket,
              std::move(hook)
          )
      ) {}

MpmcRing::~MpmcRing() = default;

bool MpmcRing::try_push(
    Value value
) {
    return impl_->try_push(
        value
    );
}

bool MpmcRing::try_push_batch(
    const std::vector<Value>& values
) {
    return impl_->try_push_batch(
        values
    );
}

std::optional<Value>
MpmcRing::try_pop() {
    return impl_->try_pop();
}

std::optional<
    std::vector<Value>
>
MpmcRing::try_pop_batch(
    std::size_t count
) {
    return impl_->try_pop_batch(
        count
    );
}

void MpmcRing::close() {
    impl_->close();
}

bool MpmcRing::closed() const noexcept {
    return impl_->closed();
}

std::size_t
MpmcRing::capacity() const noexcept {
    return impl_->capacity();
}

}  // namespace dynamo
