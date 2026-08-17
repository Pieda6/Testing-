#include "mpmc_ring.h"

#include <atomic>
#include <cstdint>
#include <memory>
#include <mutex>
#include <stdexcept>
#include <utility>
#include <vector>

namespace dynamo {

class MpmcRing::Impl {
public:
    struct Slot {
        std::atomic<Ticket> sequence{0};
        Value value = 0;
    };

    Impl(
        std::size_t capacity,
        Ticket initial_ticket,
        ObservationHook hook
    )
        : capacity_(capacity),
          mask_(capacity - 1),
          slots_(nullptr),
          enqueue_ticket_(initial_ticket),
          dequeue_ticket_(initial_ticket),
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

        slots_ = std::make_unique<Slot[]>(
            capacity_
        );

        for (
            std::size_t offset = 0;
            offset < capacity_;
            ++offset
        ) {
            const Ticket ticket =
                initial_ticket
                + static_cast<Ticket>(
                    offset
                );

            slots_[
                slot_index(ticket)
            ].sequence.store(
                ticket,
                std::memory_order_relaxed
            );
        }
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

        const Ticket observed_candidate =
            enqueue_ticket_.load(
                std::memory_order_acquire
            );

        if (
            !producer_range_available(
                observed_candidate,
                values.size()
            )
        ) {
            return false;
        }

        invoke_hook(
            HookPoint::producer_candidate,
            observed_candidate,
            values.size()
        );

        Ticket first = 0;

        {
            std::lock_guard<std::mutex> lock(
                producer_reservation_mutex_
            );

            if (
                closed_.load(
                    std::memory_order_acquire
                )
            ) {
                return false;
            }

            first =
                enqueue_ticket_.load(
                    std::memory_order_relaxed
                );

            if (
                !producer_range_available(
                    first,
                    values.size()
                )
            ) {
                return false;
            }

            enqueue_ticket_.store(
                first
                    + static_cast<Ticket>(
                        values.size()
                    ),
                std::memory_order_release
            );
        }

        invoke_hook(
            HookPoint::producer_reserved,
            first,
            values.size()
        );

        for (
            std::size_t offset = 0;
            offset < values.size();
            ++offset
        ) {
            const Ticket ticket =
                first
                + static_cast<Ticket>(
                    offset
                );

            slots_[
                slot_index(ticket)
            ].value = values[offset];
        }

        /*
         * Every payload is written before publication
         * begins. Publishing the logical first slot last
         * prevents a consumer at the FIFO frontier from
         * observing a proper prefix of this producer range.
         */
        for (
            std::size_t remaining =
                values.size();
            remaining > 0;
            --remaining
        ) {
            const std::size_t offset =
                remaining - 1;

            const Ticket ticket =
                first
                + static_cast<Ticket>(
                    offset
                );

            slots_[
                slot_index(ticket)
            ].sequence.store(
                ticket + Ticket{1},
                std::memory_order_release
            );
        }

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

        const Ticket observed_candidate =
            dequeue_ticket_.load(
                std::memory_order_acquire
            );

        if (
            !consumer_range_available(
                observed_candidate,
                count
            )
        ) {
            return std::nullopt;
        }

        invoke_hook(
            HookPoint::consumer_candidate,
            observed_candidate,
            count
        );

        Ticket first = 0;

        {
            std::lock_guard<std::mutex> lock(
                consumer_reservation_mutex_
            );

            first =
                dequeue_ticket_.load(
                    std::memory_order_relaxed
                );

            if (
                !consumer_range_available(
                    first,
                    count
                )
            ) {
                return std::nullopt;
            }

            dequeue_ticket_.store(
                first
                    + static_cast<Ticket>(
                        count
                    ),
                std::memory_order_release
            );
        }

        invoke_hook(
            HookPoint::consumer_reserved,
            first,
            count
        );

        std::vector<Value> values;
        values.reserve(count);

        /*
         * Obtain every payload before making any physical
         * slot in the owned range reusable.
         */
        for (
            std::size_t offset = 0;
            offset < count;
            ++offset
        ) {
            const Ticket ticket =
                first
                + static_cast<Ticket>(
                    offset
                );

            values.push_back(
                slots_[
                    slot_index(ticket)
                ].value
            );
        }

        for (
            std::size_t offset = 0;
            offset < count;
            ++offset
        ) {
            const Ticket ticket =
                first
                + static_cast<Ticket>(
                    offset
                );

            slots_[
                slot_index(ticket)
            ].sequence.store(
                ticket
                    + static_cast<Ticket>(
                        capacity_
                    ),
                std::memory_order_release
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
        /*
         * Close and producer ownership share this short
         * transition lock. No hook or payload work occurs
         * while it is held.
         */
        std::lock_guard<std::mutex> lock(
            producer_reservation_mutex_
        );

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

    bool producer_range_available(
        Ticket first,
        std::size_t count
    ) const {
        for (
            std::size_t offset = 0;
            offset < count;
            ++offset
        ) {
            const Ticket ticket =
                first
                + static_cast<Ticket>(
                    offset
                );

            const Ticket observed =
                slots_[
                    slot_index(ticket)
                ].sequence.load(
                    std::memory_order_acquire
                );

            if (observed != ticket) {
                return false;
            }
        }

        return true;
    }

    bool consumer_range_available(
        Ticket first,
        std::size_t count
    ) const {
        for (
            std::size_t offset = 0;
            offset < count;
            ++offset
        ) {
            const Ticket ticket =
                first
                + static_cast<Ticket>(
                    offset
                );

            const Ticket observed =
                slots_[
                    slot_index(ticket)
                ].sequence.load(
                    std::memory_order_acquire
                );

            if (
                observed
                != ticket + Ticket{1}
            ) {
                return false;
            }
        }

        return true;
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

    std::unique_ptr<Slot[]> slots_;

    std::atomic<Ticket> enqueue_ticket_;
    std::atomic<Ticket> dequeue_ticket_;

    std::mutex producer_reservation_mutex_;
    std::mutex consumer_reservation_mutex_;

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
