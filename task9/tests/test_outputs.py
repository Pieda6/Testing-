import os
import secrets
import stat
import subprocess
from pathlib import Path

import pytest


ARTIFACT = Path("/app/src/mpmc_ring.cpp")
MAX_ARTIFACT_BYTES = 2 * 1024 * 1024

# Chosen fresh for this verification run, after the submission was written, and
# echoed back by the harness only once a scenario has run to its end. The
# submission is compiled into that process and can exit zero whenever it likes;
# it cannot report a scenario it did not complete.
RUN_TOKEN = secrets.token_hex(8)


TRUSTED_HEADER = r"""#pragma once

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

using ObservationHook =
    std::function<void(HookPoint, Ticket, std::size_t)>;

class MpmcRing {
public:
    explicit MpmcRing(
        std::size_t capacity,
        Ticket initial_ticket = 0,
        ObservationHook hook = {}
    );

    ~MpmcRing();

    MpmcRing(const MpmcRing&) = delete;
    MpmcRing& operator=(const MpmcRing&) = delete;
    MpmcRing(MpmcRing&&) = delete;
    MpmcRing& operator=(MpmcRing&&) = delete;

    bool try_push(Value value);

    bool try_push_batch(
        const std::vector<Value>& values
    );

    std::optional<Value> try_pop();

    std::optional<std::vector<Value>>
    try_pop_batch(std::size_t count);

    void close();

    bool closed() const noexcept;

    std::size_t capacity() const noexcept;

private:
    class Impl;
    std::unique_ptr<Impl> impl_;
};

}
"""


HARNESS = r"""
#include "mpmc_ring.h"

#include <algorithm>
#include <atomic>
#include <chrono>
#include <condition_variable>
#include <cstdint>
#include <iostream>
#include <limits>
#include <mutex>
#include <optional>
#include <stdexcept>
#include <string>
#include <thread>
#include <vector>

using namespace std::chrono_literals;

using dynamo::HookPoint;
using dynamo::MpmcRing;
using dynamo::Ticket;
using dynamo::Value;

namespace {

thread_local int actor_tag = 0;

[[noreturn]]
void fail(
    const std::string& message
) {
    throw std::runtime_error(message);
}

void require(
    bool condition,
    const std::string& message
) {
    if (!condition) {
        fail(message);
    }
}

void require_values(
    const std::optional<std::vector<Value>>& got,
    std::initializer_list<Value> expected,
    const std::string& message
) {
    require(
        got.has_value(),
        message + ": missing"
    );

    require(
        *got == std::vector<Value>(expected),
        message + ": wrong values"
    );
}

struct Gate {
    std::mutex mutex;
    std::condition_variable cv;

    bool entered = false;
    bool released = false;

    void block() {
        std::unique_lock<std::mutex> lock(
            mutex
        );

        entered = true;
        cv.notify_all();

        cv.wait(
            lock,
            [&] {
                return released;
            }
        );
    }

    bool wait(
        std::chrono::milliseconds duration =
            1500ms
    ) {
        std::unique_lock<std::mutex> lock(
            mutex
        );

        return cv.wait_for(
            lock,
            duration,
            [&] {
                return entered;
            }
        );
    }

    void release() {
        std::lock_guard<std::mutex> lock(
            mutex
        );

        released = true;
        cv.notify_all();
    }
};

bool wait_flag(
    const std::atomic<bool>& flag,
    std::chrono::milliseconds duration =
        1000ms
) {
    const auto deadline =
        std::chrono::steady_clock::now()
        + duration;

    while (
        std::chrono::steady_clock::now()
        < deadline
    ) {
        if (
            flag.load(
                std::memory_order_acquire
            )
        ) {
            return true;
        }

        std::this_thread::sleep_for(
            1ms
        );
    }

    return flag.load(
        std::memory_order_acquire
    );
}


void basic() {
    bool threw = false;

    try {
        MpmcRing ring(0);
    } catch (
        const std::invalid_argument&
    ) {
        threw = true;
    }

    require(
        threw,
        "capacity 0 accepted"
    );

    threw = false;

    try {
        MpmcRing ring(3);
    } catch (
        const std::invalid_argument&
    ) {
        threw = true;
    }

    require(
        threw,
        "capacity 3 accepted"
    );

    MpmcRing ring(4, 7);

    require(
        ring.capacity() == 4,
        "capacity mismatch"
    );

    threw = false;

    try {
        ring.try_push_batch({});
    } catch (
        const std::invalid_argument&
    ) {
        threw = true;
    }

    require(
        threw,
        "empty push batch accepted"
    );

    threw = false;

    try {
        ring.try_pop_batch(0);
    } catch (
        const std::invalid_argument&
    ) {
        threw = true;
    }

    require(
        threw,
        "zero pop batch accepted"
    );

    require(
        ring.try_push(10),
        "single push failed"
    );

    require(
        ring.try_push_batch(
            {20, 30}
        ),
        "batch push failed"
    );

    const auto first =
        ring.try_pop();

    require(
        first && *first == 10,
        "single FIFO mismatch"
    );

    require_values(
        ring.try_pop_batch(2),
        {20, 30},
        "batch FIFO"
    );

    require(
        ring.try_push_batch(
            {40, 50, 60, 70}
        ),
        "full-size batch failed"
    );

    require(
        !ring.try_push(80),
        "push succeeded on full ring"
    );

    require_values(
        ring.try_pop_batch(4),
        {40, 50, 60, 70},
        "full drain"
    );

    require(
        !ring.try_pop(),
        "empty pop returned value"
    );

    ring.close();

    require(
        ring.closed(),
        "closed() stayed false"
    );

    require(
        !ring.try_push(90),
        "post-close push succeeded"
    );

    require(
        !ring.try_pop(),
        "closed drained ring returned value"
    );
}


void atomic_failure() {
    MpmcRing ring(
        4,
        std::numeric_limits<Ticket>::max()
            - Ticket{1}
    );

    require(
        ring.try_push_batch(
            {1, 2, 3}
        ),
        "initial batch failed"
    );

    require(
        !ring.try_push_batch(
            {4, 5}
        ),
        "insufficient-space batch succeeded"
    );

    const auto first =
        ring.try_pop();

    require(
        first && *first == 1,
        "failed push changed FIFO"
    );

    require(
        ring.try_push_batch(
            {4, 5}
        ),
        "failed push consumed producer state"
    );

    require_values(
        ring.try_pop_batch(4),
        {2, 3, 4, 5},
        "push rollback"
    );

    MpmcRing second(8, 44);

    require(
        second.try_push_batch(
            {7, 8}
        ),
        "pop rollback setup failed"
    );

    require(
        !second.try_pop_batch(3),
        "insufficient pop batch succeeded"
    );

    const auto seven =
        second.try_pop();

    require(
        seven && *seven == 7,
        "failed pop consumed first value"
    );

    const auto eight =
        second.try_pop();

    require(
        eight && *eight == 8,
        "failed pop disturbed second value"
    );
}


void boundary() {
    const std::vector<Ticket> starts = {
        Ticket{
            0x7ffffffffffffffdULL
        },
        Ticket{
            0xfffffffffffffffdULL
        },
    };

    for (
        const Ticket start :
        starts
    ) {
        MpmcRing ring(
            8,
            start
        );

        require(
            !ring.try_pop_batch(3),
            "boundary empty ring across wrap"
        );

        Value next = 1;

        for (
            int cycle = 0;
            cycle < 24;
            ++cycle
        ) {
            std::vector<Value>
                first_batch;

            for (
                int index = 0;
                index < 5;
                ++index
            ) {
                first_batch.push_back(
                    next++
                );
            }

            require(
                ring.try_push_batch(
                    first_batch
                ),
                "boundary push5 failed"
            );

            const auto prefix =
                ring.try_pop_batch(3);

            require(
                prefix
                    && *prefix
                        == std::vector<Value>(
                            first_batch.begin(),
                            first_batch.begin()
                                + 3
                        ),
                "boundary prefix mismatch"
            );

            std::vector<Value>
                second_batch;

            for (
                int index = 0;
                index < 3;
                ++index
            ) {
                second_batch.push_back(
                    next++
                );
            }

            require(
                ring.try_push_batch(
                    second_batch
                ),
                "boundary push3 failed"
            );

            std::vector<Value> expected(
                first_batch.begin() + 3,
                first_batch.end()
            );

            expected.insert(
                expected.end(),
                second_batch.begin(),
                second_batch.end()
            );

            const auto tail =
                ring.try_pop_batch(5);

            require(
                tail && *tail == expected,
                "boundary tail mismatch"
            );

            require(
                !ring.try_pop(),
                "boundary ring not empty"
            );
        }
    }
}


void producer_progress() {
    Gate gate;

    const Ticket first_ticket = 100;

    std::atomic<bool> armed{true};

    MpmcRing ring(
        8,
        first_ticket,
        [&](
            HookPoint point,
            Ticket ticket,
            std::size_t count
        ) {
            if (
                point
                    == HookPoint::
                        producer_reserved
                && ticket == first_ticket
                && count == 3
                && armed.exchange(false)
            ) {
                gate.block();
            }
        }
    );

    bool first_result = false;
    bool second_result = false;

    std::atomic<bool>
        second_done{false};

    std::thread first(
        [&] {
            first_result =
                ring.try_push_batch(
                    {1, 2, 3}
                );
        }
    );

    const bool entered =
        gate.wait();

    if (!entered) {
        gate.release();
        first.join();

        fail(
            "first producer never reserved"
        );
    }

    std::thread second(
        [&] {
            second_result =
                ring.try_push_batch(
                    {4, 5}
                );

            second_done.store(
                true,
                std::memory_order_release
            );
        }
    );

    const bool progressed =
        wait_flag(
            second_done,
            700ms
        );

    const auto early =
        ring.try_pop();

    gate.release();

    first.join();
    second.join();

    require(
        progressed,
        "later producer blocked by "
        "stalled reservation"
    );

    require(
        !early,
        "later range bypassed "
        "unpublished earlier range"
    );

    require(
        first_result
            && second_result,
        "producer operation failed"
    );

    require_values(
        ring.try_pop_batch(5),
        {1, 2, 3, 4, 5},
        "producer logical order"
    );
}


void consumer_progress() {
    Gate gate;

    const Ticket first_ticket = 200;

    std::atomic<bool> armed{true};

    MpmcRing ring(
        8,
        first_ticket,
        [&](
            HookPoint point,
            Ticket ticket,
            std::size_t count
        ) {
            if (
                point
                    == HookPoint::
                        consumer_reserved
                && ticket == first_ticket
                && count == 2
                && armed.exchange(false)
            ) {
                gate.block();
            }
        }
    );

    require(
        ring.try_push_batch(
            {10, 11, 12, 13}
        ),
        "consumer setup failed"
    );

    std::optional<
        std::vector<Value>
    > first_values;

    std::optional<
        std::vector<Value>
    > second_values;

    std::atomic<bool>
        second_done{false};

    std::thread first(
        [&] {
            first_values =
                ring.try_pop_batch(2);
        }
    );

    const bool entered =
        gate.wait();

    if (!entered) {
        gate.release();
        first.join();

        fail(
            "first consumer never reserved"
        );
    }

    std::thread second(
        [&] {
            second_values =
                ring.try_pop_batch(2);

            second_done.store(
                true,
                std::memory_order_release
            );
        }
    );

    const bool progressed =
        wait_flag(
            second_done,
            700ms
        );

    gate.release();

    first.join();
    second.join();

    require(
        progressed,
        "later consumer blocked by "
        "stalled reservation"
    );

    require(
        first_values
            && *first_values
                == std::vector<Value>(
                    {10, 11}
                ),
        "first consumer values wrong"
    );

    require(
        second_values
            && *second_values
                == std::vector<Value>(
                    {12, 13}
                ),
        "second consumer values wrong"
    );

    require(
        ring.try_push_batch(
            {50, 60, 70, 80}
        ),
        "released slots not reusable"
    );

    require_values(
        ring.try_pop_batch(4),
        {50, 60, 70, 80},
        "post-release values"
    );
}


void close_reserved() {
    Gate gate;

    const Ticket first_ticket = 300;

    std::atomic<bool> armed{true};

    MpmcRing ring(
        8,
        first_ticket,
        [&](
            HookPoint point,
            Ticket ticket,
            std::size_t count
        ) {
            if (
                point
                    == HookPoint::
                        producer_reserved
                && ticket == first_ticket
                && count == 3
                && armed.exchange(false)
            ) {
                gate.block();
            }
        }
    );

    bool pushed = false;

    std::thread producer(
        [&] {
            pushed =
                ring.try_push_batch(
                    {71, 72, 73}
                );
        }
    );

    const bool entered =
        gate.wait();

    if (!entered) {
        gate.release();
        producer.join();

        fail(
            "producer never reserved "
            "before close"
        );
    }

    std::atomic<bool>
        close_done{false};

    std::thread closer(
        [&] {
            ring.close();

            close_done.store(
                true,
                std::memory_order_release
            );
        }
    );

    const bool close_progressed =
        wait_flag(
            close_done,
            700ms
        );

    if (!close_progressed) {
        gate.release();
    }

    closer.join();

    const bool post_close_push =
        ring.try_push(74);

    gate.release();

    producer.join();

    require(
        close_progressed,
        "close blocked behind "
        "owned producer"
    );

    require(
        ring.closed(),
        "close not visible"
    );

    require(
        !post_close_push,
        "post-close producer "
        "obtained ownership"
    );

    require(
        pushed,
        "close revoked owned batch"
    );

    require_values(
        ring.try_pop_batch(3),
        {71, 72, 73},
        "owned batch not drainable"
    );

    require(
        !ring.try_pop(),
        "closed ring not drained"
    );
}


void reuse() {
    const Ticket first_ticket =
        std::numeric_limits<Ticket>::max();

    Gate gate;

    std::atomic<bool> armed{true};

    MpmcRing ring(
        2,
        first_ticket,
        [&](
            HookPoint point,
            Ticket ticket,
            std::size_t count
        ) {
            if (
                point
                    == HookPoint::
                        consumer_reserved
                && ticket == first_ticket
                && count == 1
                && armed.exchange(false)
            ) {
                gate.block();
            }
        }
    );

    require(
        ring.try_push_batch(
            {501, 502}
        ),
        "reuse setup failed"
    );

    std::optional<Value>
        first_value;

    std::optional<Value>
        second_value;

    std::atomic<bool>
        second_done{false};

    std::thread first(
        [&] {
            first_value =
                ring.try_pop();
        }
    );

    const bool entered =
        gate.wait();

    if (!entered) {
        gate.release();
        first.join();

        fail(
            "reuse consumer "
            "never reserved"
        );
    }

    std::thread second(
        [&] {
            second_value =
                ring.try_pop();

            second_done.store(
                true,
                std::memory_order_release
            );
        }
    );

    const bool progressed =
        wait_flag(
            second_done,
            700ms
        );

    const bool premature_reuse =
        ring.try_push(503);

    gate.release();

    first.join();
    second.join();

    require(
        progressed,
        "second consumer blocked "
        "in reuse schedule"
    );

    require(
        !premature_reuse,
        "slot reused before prior "
        "consumer released it"
    );

    require(
        first_value
            && *first_value == 501,
        "reuse first value wrong"
    );

    require(
        second_value
            && *second_value == 502,
        "reuse second value wrong"
    );

    require(
        ring.try_push(503),
        "slot not reusable "
        "after release"
    );

    const auto reused =
        ring.try_pop();

    require(
        reused && *reused == 503,
        "reused slot value wrong"
    );
}


void producer_candidate_overtake() {
    Gate candidate_gate;
    Gate reserved_gate;

    const Ticket start = 1000;

    std::atomic<int>
        first_candidate_calls{0};

    std::atomic<bool>
        metadata_ok{true};

    MpmcRing ring(
        8,
        start,
        [&](
            HookPoint point,
            Ticket ticket,
            std::size_t count
        ) {
            if (
                point
                    == HookPoint::
                        producer_candidate
                && actor_tag == 1
            ) {
                first_candidate_calls
                    .fetch_add(
                        1,
                        std::memory_order_relaxed
                    );

                if (
                    ticket != start
                    || count != 3
                ) {
                    metadata_ok.store(
                        false,
                        std::memory_order_relaxed
                    );
                }

                candidate_gate.block();
            }

            if (
                point
                    == HookPoint::
                        producer_reserved
                && actor_tag == 2
            ) {
                if (
                    ticket != start
                    || count != 2
                ) {
                    metadata_ok.store(
                        false,
                        std::memory_order_relaxed
                    );
                }

                reserved_gate.block();
            }
        }
    );

    bool first_result = false;
    bool second_result = false;

    std::atomic<bool>
        first_done{false};

    std::thread first(
        [&] {
            actor_tag = 1;

            first_result =
                ring.try_push_batch(
                    {100, 101, 102}
                );

            first_done.store(
                true,
                std::memory_order_release
            );
        }
    );

    const bool candidate_entered =
        candidate_gate.wait();

    if (!candidate_entered) {
        candidate_gate.release();
        first.join();

        fail(
            "first producer never "
            "reached candidate hook"
        );
    }

    std::thread second(
        [&] {
            actor_tag = 2;

            second_result =
                ring.try_push_batch(
                    {200, 201}
                );
        }
    );

    const bool second_reserved =
        reserved_gate.wait();

    if (!second_reserved) {
        candidate_gate.release();
        reserved_gate.release();

        first.join();
        second.join();

        fail(
            "second producer could not "
            "overtake stalled candidate"
        );
    }

    candidate_gate.release();

    const bool first_rebased =
        wait_flag(
            first_done,
            700ms
        );

    const auto early =
        ring.try_pop();

    reserved_gate.release();

    first.join();
    second.join();

    require(
        metadata_ok.load(
            std::memory_order_relaxed
        ),
        "producer candidate hook "
        "metadata wrong"
    );

    require(
        first_candidate_calls.load(
            std::memory_order_relaxed
        ) == 1,
        "producer candidate hook "
        "repeated during retry"
    );

    require(
        first_rebased,
        "stale producer candidate "
        "did not rebase while earlier "
        "range remained reserved"
    );

    require(
        first_result,
        "stale producer candidate "
        "incorrectly failed"
    );

    require(
        second_result,
        "overtaking producer failed"
    );

    require(
        !early,
        "later published range became "
        "visible before earlier "
        "reserved range"
    );

    require_values(
        ring.try_pop_batch(5),
        {200, 201, 100, 101, 102},
        "producer candidate ownership order"
    );
}


void consumer_candidate_overtake() {
    Gate candidate_gate;
    Gate reserved_gate;

    const Ticket start = 2000;

    std::atomic<int>
        first_candidate_calls{0};

    std::atomic<bool>
        metadata_ok{true};

    MpmcRing ring(
        8,
        start,
        [&](
            HookPoint point,
            Ticket ticket,
            std::size_t count
        ) {
            if (
                point
                    == HookPoint::
                        consumer_candidate
                && actor_tag == 1
            ) {
                first_candidate_calls
                    .fetch_add(
                        1,
                        std::memory_order_relaxed
                    );

                if (
                    ticket != start
                    || count != 3
                ) {
                    metadata_ok.store(
                        false,
                        std::memory_order_relaxed
                    );
                }

                candidate_gate.block();
            }

            if (
                point
                    == HookPoint::
                        consumer_reserved
                && actor_tag == 2
            ) {
                if (
                    ticket != start
                    || count != 2
                ) {
                    metadata_ok.store(
                        false,
                        std::memory_order_relaxed
                    );
                }

                reserved_gate.block();
            }
        }
    );

    require(
        ring.try_push_batch(
            {1, 2, 3, 4, 5}
        ),
        "consumer candidate "
        "setup failed"
    );

    std::optional<
        std::vector<Value>
    > first_values;

    std::optional<
        std::vector<Value>
    > second_values;

    std::atomic<bool>
        first_done{false};

    std::thread first(
        [&] {
            actor_tag = 1;

            first_values =
                ring.try_pop_batch(3);

            first_done.store(
                true,
                std::memory_order_release
            );
        }
    );

    const bool candidate_entered =
        candidate_gate.wait();

    if (!candidate_entered) {
        candidate_gate.release();
        first.join();

        fail(
            "first consumer never "
            "reached candidate hook"
        );
    }

    std::thread second(
        [&] {
            actor_tag = 2;

            second_values =
                ring.try_pop_batch(2);
        }
    );

    const bool second_reserved =
        reserved_gate.wait();

    if (!second_reserved) {
        candidate_gate.release();
        reserved_gate.release();

        first.join();
        second.join();

        fail(
            "second consumer could not "
            "overtake stalled candidate"
        );
    }

    candidate_gate.release();

    const bool first_rebased =
        wait_flag(
            first_done,
            700ms
        );

    reserved_gate.release();

    first.join();
    second.join();

    require(
        metadata_ok.load(
            std::memory_order_relaxed
        ),
        "consumer candidate hook "
        "metadata wrong"
    );

    require(
        first_candidate_calls.load(
            std::memory_order_relaxed
        ) == 1,
        "consumer candidate hook "
        "repeated during retry"
    );

    require(
        first_rebased,
        "stale consumer candidate "
        "did not rebase while earlier "
        "consumer remained reserved"
    );

    require(
        first_values
            && *first_values
                == std::vector<Value>(
                    {3, 4, 5}
                ),
        "rebased consumer returned "
        "wrong range"
    );

    require(
        second_values
            && *second_values
                == std::vector<Value>(
                    {1, 2}
                ),
        "overtaking consumer returned "
        "wrong range"
    );

    require(
        !ring.try_pop(),
        "consumer candidate schedule "
        "did not drain ring"
    );
}


void close_candidate() {
    Gate candidate_gate;

    const Ticket start = 3000;

    std::atomic<int>
        candidate_calls{0};

    std::atomic<bool>
        metadata_ok{true};

    MpmcRing ring(
        4,
        start,
        [&](
            HookPoint point,
            Ticket ticket,
            std::size_t count
        ) {
            if (
                point
                    == HookPoint::
                        producer_candidate
                && actor_tag == 1
            ) {
                candidate_calls.fetch_add(
                    1,
                    std::memory_order_relaxed
                );

                if (
                    ticket != start
                    || count != 2
                ) {
                    metadata_ok.store(
                        false,
                        std::memory_order_relaxed
                    );
                }

                candidate_gate.block();
            }
        }
    );

    bool result = true;

    std::thread producer(
        [&] {
            actor_tag = 1;

            result =
                ring.try_push_batch(
                    {9, 10}
                );
        }
    );

    const bool entered =
        candidate_gate.wait();

    if (!entered) {
        candidate_gate.release();
        producer.join();

        fail(
            "producer never reached "
            "candidate before close"
        );
    }

    std::atomic<bool>
        close_done{false};

    std::thread closer(
        [&] {
            ring.close();

            close_done.store(
                true,
                std::memory_order_release
            );
        }
    );

    const bool close_progressed =
        wait_flag(
            close_done,
            700ms
        );

    if (!close_progressed) {
        candidate_gate.release();
    }

    closer.join();

    const bool post_close_push =
        ring.try_push(11);

    candidate_gate.release();

    producer.join();

    require(
        metadata_ok.load(
            std::memory_order_relaxed
        ),
        "close candidate metadata wrong"
    );

    require(
        candidate_calls.load(
            std::memory_order_relaxed
        ) == 1,
        "candidate hook repeated"
    );

    require(
        close_progressed,
        "close blocked behind "
        "pre-ownership candidate"
    );

    require(
        ring.closed(),
        "closed state not visible"
    );

    require(
        !result,
        "candidate acquired ownership "
        "after close won"
    );

    require(
        !post_close_push,
        "new push succeeded after close"
    );

    require(
        !ring.try_pop(),
        "failed candidate published data"
    );
}


void mixed() {
    constexpr int producer_count = 4;
    constexpr int consumer_count = 4;
    constexpr int values_per_producer = 240;

    MpmcRing ring(
        64,
        0xfffffffffffffff0ULL
    );

    std::mutex output_mutex;

    std::vector<Value> output;
    std::vector<Value> expected;

    expected.reserve(
        producer_count
        * values_per_producer
    );

    for (
        int producer = 0;
        producer < producer_count;
        ++producer
    ) {
        for (
            int index = 0;
            index < values_per_producer;
            ++index
        ) {
            expected.push_back(
                static_cast<Value>(
                    producer + 1
                )
                    * 1000000ULL
                + static_cast<Value>(
                    index
                )
            );
        }
    }

    std::atomic<int>
        producers_done{0};

    std::vector<std::thread>
        consumers;

    for (
        int consumer = 0;
        consumer < consumer_count;
        ++consumer
    ) {
        consumers.emplace_back(
            [&, consumer] {
                for (;;) {
                    bool obtained = false;

                    const std::size_t wanted =
                        static_cast<std::size_t>(
                            2
                            + (
                                consumer
                                % 3
                            )
                        );

                    auto batch =
                        ring.try_pop_batch(
                            wanted
                        );

                    if (batch) {
                        std::lock_guard<
                            std::mutex
                        > lock(
                            output_mutex
                        );

                        output.insert(
                            output.end(),
                            batch->begin(),
                            batch->end()
                        );

                        obtained = true;
                    } else {
                        const auto one =
                            ring.try_pop();

                        if (one) {
                            std::lock_guard<
                                std::mutex
                            > lock(
                                output_mutex
                            );

                            output.push_back(
                                *one
                            );

                            obtained = true;
                        }
                    }

                    if (obtained) {
                        continue;
                    }

                    if (
                        ring.closed()
                        && producers_done.load(
                            std::memory_order_acquire
                        ) == producer_count
                    ) {
                        const auto last =
                            ring.try_pop();

                        if (!last) {
                            break;
                        }

                        std::lock_guard<
                            std::mutex
                        > lock(
                            output_mutex
                        );

                        output.push_back(
                            *last
                        );
                    } else {
                        std::this_thread::yield();
                    }
                }
            }
        );
    }

    std::vector<std::thread>
        producers;

    for (
        int producer = 0;
        producer < producer_count;
        ++producer
    ) {
        producers.emplace_back(
            [&, producer] {
                int index = 0;

                while (
                    index
                    < values_per_producer
                ) {
                    int batch_size =
                        1
                        + (
                            (
                                producer
                                + index
                            )
                            % 4
                        );

                    if (
                        index + batch_size
                        > values_per_producer
                    ) {
                        batch_size =
                            values_per_producer
                            - index;
                    }

                    std::vector<Value>
                        batch;

                    for (
                        int offset = 0;
                        offset < batch_size;
                        ++offset
                    ) {
                        batch.push_back(
                            static_cast<Value>(
                                producer + 1
                            )
                                * 1000000ULL
                            + static_cast<Value>(
                                index + offset
                            )
                        );
                    }

                    while (
                        !ring.try_push_batch(
                            batch
                        )
                    ) {
                        std::this_thread::yield();
                    }

                    index += batch_size;
                }

                producers_done.fetch_add(
                    1,
                    std::memory_order_release
                );
            }
        );
    }

    for (
        auto& producer :
        producers
    ) {
        producer.join();
    }

    ring.close();

    for (
        auto& consumer :
        consumers
    ) {
        consumer.join();
    }

    require(
        output.size()
            == expected.size(),
        "mixed delivery count mismatch"
    );

    std::sort(
        output.begin(),
        output.end()
    );

    std::sort(
        expected.begin(),
        expected.end()
    );

    require(
        output == expected,
        "mixed exact-once "
        "delivery mismatch"
    );

    require(
        !ring.try_pop(),
        "mixed ring not drained"
    );
}

}  // namespace


int main(
    int argc,
    char** argv
) {
    try {
        if (argc != 3) {
            fail(
                "scenario and run token required"
            );
        }

        const std::string scenario =
            argv[1];

        const std::string token =
            argv[2];

        if (scenario == "s0") {
            basic();
        } else if (
            scenario == "s1"
        ) {
            atomic_failure();
        } else if (
            scenario == "s2"
        ) {
            boundary();
        } else if (
            scenario == "s3"
        ) {
            producer_progress();
        } else if (
            scenario == "s4"
        ) {
            consumer_progress();
        } else if (
            scenario == "s5"
        ) {
            close_reserved();
        } else if (
            scenario == "s6"
        ) {
            reuse();
        } else if (
            scenario == "s7"
        ) {
            producer_candidate_overtake();
        } else if (
            scenario == "s8"
        ) {
            consumer_candidate_overtake();
        } else if (
            scenario == "s9"
        ) {
            close_candidate();
        } else if (
            scenario == "s10"
        ) {
            mixed();
        } else {
            fail(
                "unknown scenario"
            );
        }

        /*
         * The submission is compiled into this process, so exiting zero is
         * something it can do for itself. Completing the scenario is not:
         * this line is reached only by running the whole of it, and the
         * caller checks for it with a token it chose after the build.
         */
        std::cout
            << token
            << " "
            << scenario
            << " completed\n";

        return 0;
    } catch (
        const std::exception& error
    ) {
        std::cerr
            << error.what()
            << "\n";

        return 1;
    }
}
"""


def _read_regular_file(
    path: Path,
) -> bytes:
    flags = (
        os.O_RDONLY
        | getattr(
            os,
            "O_CLOEXEC",
            0,
        )
        | getattr(
            os,
            "O_NOFOLLOW",
            0,
        )
    )

    try:
        fd = os.open(
            path,
            flags,
        )
    except OSError as exc:
        pytest.fail(
            "graded artifact is missing "
            f"or unsafe: {exc}"
        )

    try:
        info = os.fstat(fd)

        if not stat.S_ISREG(
            info.st_mode
        ):
            pytest.fail(
                "graded artifact must "
                "be a regular file"
            )

        if (
            info.st_size
            > MAX_ARTIFACT_BYTES
        ):
            pytest.fail(
                "graded artifact is "
                "unexpectedly large"
            )

        chunks = []

        while True:
            chunk = os.read(
                fd,
                65536,
            )

            if not chunk:
                break

            chunks.append(chunk)

        return b"".join(chunks)
    finally:
        os.close(fd)


@pytest.fixture(scope="session")
def harness_binary(
    tmp_path_factory:
        pytest.TempPathFactory,
) -> Path:
    build = (
        tmp_path_factory.mktemp(
            "mpmc-build"
        )
    )

    source = (
        build / "mpmc_ring.cpp"
    )

    header = (
        build / "mpmc_ring.h"
    )

    harness = (
        build / "harness.cpp"
    )

    binary = (
        build / "mpmc_harness"
    )

    source.write_bytes(
        _read_regular_file(
            ARTIFACT
        )
    )

    header.write_text(
        TRUSTED_HEADER,
        encoding="utf-8",
    )

    harness.write_text(
        HARNESS,
        encoding="utf-8",
    )

    command = [
        "/usr/bin/g++",
        "-std=c++20",
        "-O1",
        "-g",
        "-Wall",
        "-Wextra",
        "-Wpedantic",
        "-Werror",
        "-pthread",
        "-fsanitize=undefined",
        "-fno-sanitize-recover=undefined",
        "-I",
        str(build),
        str(source),
        str(harness),
        "-o",
        str(binary),
    ]

    result = subprocess.run(
        command,
        text=True,
        capture_output=True,
        timeout=30,
    )

    if result.returncode != 0:
        pytest.fail(
            "submission did not compile "
            "against the trusted API:\n"
            + result.stderr[-6000:]
        )

    return binary


def _run(
    binary: Path,
    scenario: str,
) -> None:
    env = {
        "PATH": "/usr/bin:/bin",
        "HOME": "/tmp",
        "LANG": "C",
        "LC_ALL": "C",
        "UBSAN_OPTIONS":
            "halt_on_error=1:"
            "print_stacktrace=1",
    }

    try:
        result = subprocess.run(
            [
                str(binary),
                scenario,
                RUN_TOKEN,
            ],
            text=True,
            capture_output=True,
            cwd=binary.parent,
            env=env,
            timeout=8,
        )
    except subprocess.TimeoutExpired:
        pytest.fail(
            f"scenario {scenario} "
            "timed out "
            "(probable deadlock "
            "or global stall)"
        )

    if result.returncode != 0:
        detail = (
            result.stderr
            or result.stdout
            or "scenario failed"
        ).strip()

        pytest.fail(
            detail[-4000:]
        )

    completed = (
        f"{RUN_TOKEN} {scenario} completed"
    )

    if completed not in result.stdout:
        pytest.fail(
            f"scenario {scenario} exited "
            "zero without running to the "
            "end of the scenario"
        )


SCENARIOS = [
    (
        "s0",
        "basic single and batch behavior",
    ),
    (
        "s1",
        "failed batches are atomic",
    ),
    (
        "s2",
        "ticket boundary and reuse",
    ),
    (
        "s3",
        "stalled producer progress",
    ),
    (
        "s4",
        "stalled consumer progress",
    ),
    (
        "s5",
        "close preserves owned batch",
    ),
    (
        "s6",
        "slot reuse waits for release",
    ),
    (
        "s7",
        "producer candidate overtaking",
    ),
    (
        "s8",
        "consumer candidate overtaking",
    ),
    (
        "s9",
        "close beats unowned candidate",
    ),
    (
        "s10",
        "mixed exact-once delivery",
    ),
]


@pytest.mark.parametrize(
    ("scenario", "_description"),
    SCENARIOS,
)
def test_mpmc_behavior(
    harness_binary: Path,
    scenario: str,
    _description: str,
) -> None:
    _run(
        harness_binary,
        scenario,
    )
