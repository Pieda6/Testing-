"""Single-defect battery: each defect, alone, on top of the correct solution.

A repair task is only as hard as the distance between what ships and what is
correct. This measures that distance one defect at a time. Every entry below is
applied to the reference solution by itself; the verifier must then score zero,
and the scenarios it fails are recorded. A defect no scenario catches is inert
and does not belong in the shipped artifact.

    python3 dev9/mutations.py
"""
import sys

import runner


def sub(src, old, new, count=1):
    assert src.count(old) >= count, "anchor missing: %r" % old[:70]
    return src.replace(old, new, count)


# --- anchors in the reference solution --------------------------------------

PRODUCER_TICKET_READ = """            first =
                enqueue_ticket_.load(
                    std::memory_order_relaxed
                );
"""

CONSUMER_TICKET_READ = """            first =
                dequeue_ticket_.load(
                    std::memory_order_relaxed
                );
"""

PRODUCER_AVAILABLE = """    bool producer_range_available(
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
"""

REVERSE_PUBLISH = """        for (
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
"""

FORWARD_PUBLISH = """        for (
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
            ].sequence.store(
                ticket + Ticket{1},
                std::memory_order_release
            );
        }
"""

READ_PAYLOADS = """        for (
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
"""

RELEASE_SLOTS = """        for (
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
"""

PRODUCER_CANDIDATE_HOOK = """        invoke_hook(
            HookPoint::producer_candidate,
            observed_candidate,
            values.size()
        );

"""

CONSUMER_CANDIDATE_HOOK = """        invoke_hook(
            HookPoint::consumer_candidate,
            observed_candidate,
            count
        );

"""

PRODUCER_LOCK = """            std::lock_guard<std::mutex> lock(
                producer_reservation_mutex_
            );
"""

CONSUMER_LOCK = """            std::lock_guard<std::mutex> lock(
                consumer_reservation_mutex_
            );
"""

PRODUCER_RESERVED_HOOK = """        invoke_hook(
            HookPoint::producer_reserved,
            first,
            values.size()
        );
"""


# --- the defects ------------------------------------------------------------

def producer_stale_candidate(src):
    """The reservation insists on the ticket it observed before the hook, so a
    producer that was overtaken while blocked fails instead of rebasing."""
    return sub(src, PRODUCER_TICKET_READ, PRODUCER_TICKET_READ + """
            if (first != observed_candidate) {
                return false;
            }
""")


def consumer_stale_candidate(src):
    """The same insistence on the consumer side."""
    return sub(src, CONSUMER_TICKET_READ, CONSUMER_TICKET_READ + """
            if (first != observed_candidate) {
                return std::nullopt;
            }
""")


def capacity_from_consumer_ticket(src):
    """Capacity is computed from how many tickets the consumers have taken
    rather than from which physical slots they have released, so a slot is
    handed to a new producer while its previous consumer still holds it."""
    return sub(src, PRODUCER_AVAILABLE, """    bool producer_range_available(
        Ticket first,
        std::size_t count
    ) const {
        const Ticket consumed =
            dequeue_ticket_.load(
                std::memory_order_acquire
            );

        const Ticket outstanding =
            first
            + static_cast<Ticket>(count)
            - consumed;

        return outstanding
            <= static_cast<Ticket>(capacity_);
    }
""")


def signed_capacity_compare(src):
    """On top of the ticket-difference capacity test, the comparison is signed,
    so it misreads the distance once tickets cross the signed boundary."""
    src = capacity_from_consumer_ticket(src)
    return sub(src, """        return outstanding
            <= static_cast<Ticket>(capacity_);""",
               """        return static_cast<std::int64_t>(outstanding)
            <= static_cast<std::int64_t>(capacity_);""")


def release_before_read(src):
    """Slots are handed back for reuse before their payloads are read out."""
    return sub(src, READ_PAYLOADS + "\n" + RELEASE_SLOTS,
               RELEASE_SLOTS + "\n" + READ_PAYLOADS)


def close_revokes_owned(src):
    """A defensive re-check after ownership abandons a batch the producer
    already owns when a close lands underneath it."""
    return sub(src, PRODUCER_RESERVED_HOOK, PRODUCER_RESERVED_HOOK + """
        if (
            closed_.load(
                std::memory_order_acquire
            )
        ) {
            return false;
        }
""")


def forward_publication(src):
    """Publishing the batch front to back exposes a proper prefix of it."""
    return sub(src, REVERSE_PUBLISH, FORWARD_PUBLISH)


def publish_before_payload(src):
    """The range is published before its payloads are written."""
    write = """        for (
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
"""
    assert write in src
    src = src.replace(write, "@@WRITE@@\n", 1)
    src = sub(src, REVERSE_PUBLISH, REVERSE_PUBLISH + "\n" + write)
    return src.replace("@@WRITE@@\n", "")


def producer_lock_across_hook(src):
    """The candidate observation is taken under the reservation lock and the
    lock is still held while the hook runs."""
    src = sub(src, PRODUCER_CANDIDATE_HOOK, "")
    return sub(src, PRODUCER_LOCK, PRODUCER_LOCK + """
            invoke_hook(
                HookPoint::producer_candidate,
                observed_candidate,
                values.size()
            );
""")


def consumer_lock_across_hook(src):
    """The same, on the consumer side."""
    src = sub(src, CONSUMER_CANDIDATE_HOOK, "")
    return sub(src, CONSUMER_LOCK, CONSUMER_LOCK + """
            invoke_hook(
                HookPoint::consumer_candidate,
                observed_candidate,
                count
            );
""")


def candidate_hook_per_attempt(src):
    """The candidate hook is invoked again on every internal retry."""
    return sub(src, PRODUCER_CANDIDATE_HOOK, PRODUCER_CANDIDATE_HOOK + """        invoke_hook(
            HookPoint::producer_candidate,
            observed_candidate,
            values.size()
        );

""")


def ordered_publication(src):
    """Publication is serialised in ticket order: a producer whose payload work
    is finished waits for every earlier range before publishing its own, so an
    owner stalled in its hook holds up everyone behind it."""
    src = sub(src, """          dequeue_ticket_(initial_ticket),""",
              """          dequeue_ticket_(initial_ticket),
          publish_frontier_(initial_ticket),""")
    src = sub(src, """    std::atomic<Ticket> dequeue_ticket_;""",
              """    std::atomic<Ticket> dequeue_ticket_;
    std::atomic<Ticket> publish_frontier_;""")
    src = sub(src, REVERSE_PUBLISH, """        while (
            publish_frontier_.load(
                std::memory_order_acquire
            ) != first
        ) {
            std::this_thread::yield();
        }

""" + REVERSE_PUBLISH + """
        publish_frontier_.store(
            first
                + static_cast<Ticket>(
                    values.size()
                ),
            std::memory_order_release
        );
""")
    return sub(src, "#include <stdexcept>", "#include <stdexcept>\n#include <thread>")


# Defects planted in the shipped artifact. Each must be caught on its own.
SHIPPED = [
    ("ownership: producer keeps its stale candidate", producer_stale_candidate),
    ("ownership: consumer keeps its stale candidate", consumer_stale_candidate),
    ("capacity: from consumer ticket, not release", capacity_from_consumer_ticket),
    ("publication: serialised in ticket order", ordered_publication),
    ("close: revokes an already-owned batch", close_revokes_owned),
]

# Mistakes a repair attempt introduces by itself. They are not planted; they are
# measured to show the verifier holds the line against the natural wrong fixes.
TRAPS = [
    ("retry re-fires the candidate hook", candidate_hook_per_attempt),
    ("producer lock held across the hook", producer_lock_across_hook),
    ("consumer lock held across the hook", consumer_lock_across_hook),
]

# Real violations of the contract that no scenario can catch, because the hook
# set has no observation point inside the payload-and-publication window. Left
# out of the shipped artifact rather than planted where they cannot be graded.
UNGRADEABLE = [
    ("batch published front to back", forward_publication),
    ("range published before payloads written", publish_before_payload),
    ("slots released before payloads are read", release_before_read),
]

# Measured and left out for a different reason: it is caught, but only by the
# scenarios that already catch the defect underneath it, so planting it would
# claim coverage the suite does not have.
NO_EXTRA_COVERAGE = [
    ("signed capacity compare", signed_capacity_compare,
     capacity_from_consumer_ticket),
]

# The sixth planted defect lives in arithmetic the reference does not perform,
# so it is measured the other way round: repaired alone in the shipped
# artifact. Doing so must clear s2 and nothing else, and must not pass.
NON_MODULAR = ("""        return first
            + static_cast<Ticket>(
                count
            )
            <= published;""",
               """        return published - first
            >= static_cast<Ticket>(
                count
            );""")


def report(reference, group, want_caught):
    bad = []
    for label, defect in group:
        reward, passed, failed, _out = runner.grade(defect(reference))
        note = ""
        if not passed and not failed:
            note = "   <-- did not compile or did not run"
            bad.append(label)
        elif (reward == "0") != want_caught:
            note = "   <-- expected %s" % ("reward 0" if want_caught else "reward 1")
            bad.append(label)
        print("  %-46s reward=%s  fails %-14s%s"
              % (label, reward, ",".join(failed) or "-", note))
    return bad


def main():
    reference = runner.read(runner.REFERENCE)
    reward, _passed, failed, _out = runner.grade(reference)
    print("  %-46s reward=%s  fails %s"
          % ("the reference solution", reward, ",".join(failed) or "-"))
    assert reward == "1", "the reference solution does not pass its own verifier"

    bad = []
    print("\nplanted defects, each alone on top of the reference:")
    bad += report(reference, SHIPPED, want_caught=True)
    print("\nmistakes a repair attempt makes on its own:")
    bad += report(reference, TRAPS, want_caught=True)
    print("\nviolations the hook set cannot expose (measured, not planted):")
    bad += report(reference, UNGRADEABLE, want_caught=False)

    print("\ncaught, but only by what already catches the defect beneath it:")
    for label, defect, base in NO_EXTRA_COVERAGE:
        _r, _p, with_it, _o = runner.grade(defect(reference))
        _r, _p, without, _o = runner.grade(base(reference))
        extra = sorted(set(with_it) - set(without), key=lambda s: int(s[1:]))
        print("  %-46s fails %-14s adds %s"
              % (label, ",".join(with_it), ",".join(extra) or "nothing"))
        if extra:
            bad.append("%s does add coverage after all" % label)

    print("\nthe shipped artifact, and its non-modular compare repaired alone:")
    shipped = runner.read(runner.SHIPPED)
    reward, _passed, before, _out = runner.grade(shipped)
    print("  %-46s reward=%s  fails %s"
          % ("as it ships", reward, ",".join(before)))
    if reward != "0":
        bad.append("the shipped artifact passes its own verifier")
    old, new = NON_MODULAR
    assert old in shipped, "non-modular compare anchor missing"
    reward, _passed, after, _out = runner.grade(shipped.replace(old, new, 1))
    cleared = sorted(set(before) - set(after), key=lambda s: int(s[1:]))
    print("  %-46s reward=%s  fails %-14s clears %s"
          % ("with modular ticket distance", reward, ",".join(after),
             ",".join(cleared) or "nothing"))
    if reward != "0":
        bad.append("one repair was enough to pass")
    if "s2" not in cleared:
        bad.append("the non-modular compare is not what s2 catches")

    print()
    if bad:
        print("%d entries came out wrong: %s" % (len(bad), "; ".join(bad)))
        return 1
    print("every planted defect and every repair trap is caught on its own")
    return 0


if __name__ == "__main__":
    sys.exit(main())
