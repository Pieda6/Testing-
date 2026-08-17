#pragma once

#include <cstddef>
#include <cstdint>
#include <functional>
#include <memory>
#include <optional>
#include <vector>

namespace dynamo {

using Value = std::uint64_t;
using Ticket = std::uint64_t;

enum class HookPoint {
    producer_candidate,
    producer_reserved,
    producer_published,
    consumer_candidate,
    consumer_reserved,
    consumer_released,
};

using ObservationHook = std::function<
    void(
        HookPoint,
        Ticket,
        std::size_t
    )
>;

class MpmcRing {
public:
    explicit MpmcRing(
        std::size_t capacity,
        Ticket initial_ticket = 0,
        ObservationHook hook = {}
    );

    ~MpmcRing();

    MpmcRing(
        const MpmcRing&
    ) = delete;

    MpmcRing& operator=(
        const MpmcRing&
    ) = delete;

    MpmcRing(
        MpmcRing&&
    ) = delete;

    MpmcRing& operator=(
        MpmcRing&&
    ) = delete;

    bool try_push(
        Value value
    );

    bool try_push_batch(
        const std::vector<Value>& values
    );

    std::optional<Value>
    try_pop();

    std::optional<std::vector<Value>>
    try_pop_batch(
        std::size_t count
    );

    void close();

    bool closed() const noexcept;

    std::size_t
    capacity() const noexcept;

private:
    class Impl;
    std::unique_ptr<Impl> impl_;
};

}  // namespace dynamo
