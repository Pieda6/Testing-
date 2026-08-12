# Bounded MPMC ring contract

`/app/src/mpmc_ring.cpp` is the only implementation file under repair. `/app/include/mpmc_ring.h` defines the public API and observation-hook types.

## Construction

The ring has a fixed capacity for its lifetime.

`capacity` must be a power of two and at least `2`; otherwise construction throws `std::invalid_argument`.

`initial_ticket` may be any `std::uint64_t`. It is the first logical producer and consumer ticket.

Ticket arithmetic is modulo $2^{64}$ and must remain correct across both the signed 64-bit boundary and unsigned wraparound.

Construction starts no background threads.

## Single-item operations

`try_push(value)` has the same semantics as a push batch containing one value.

`try_pop()` has the same semantics as a pop batch of count one.

## Batch push

`try_push_batch(values)` accepts between `1` and `capacity` values. An empty batch or a batch larger than the ring capacity throws `std::invalid_argument`.

A successful batch owns one contiguous logical producer-ticket range:

```text
[first_ticket, first_ticket + values.size())
```

with arithmetic modulo $2^{64}$.

Values correspond to those logical tickets in input order.

A successful ownership transition reserves the entire range atomically.

A failed batch:

- consumes no producer tickets;
- changes no payload;
- changes no slot ownership or publication state.

Physical ring wraparound does not split the logical batch.

## Producer candidate and ownership

Before producer ownership is acquired, an invocation may discover that its requested number of slots is currently eligible.

The first time an invocation observes such a complete eligible range, it invokes:

```text
HookPoint::producer_candidate
```

with that observed candidate range.

At `producer_candidate`:

- the invocation owns no producer ticket;
- no producer ticket has been consumed;
- no slot has been reserved by that invocation;
- no payload has been modified;
- another producer may acquire the same candidate range while the hook is blocked;
- `close()` may win while the hook is blocked.

Returning from `producer_candidate` does not guarantee ownership.

The invocation must revalidate current state before attempting the ownership transition.

If another producer acquired the candidate first, the stalled invocation may subsequently acquire a later eligible range.

If closure becomes visible before ownership is obtained, the producer returns `false` without consuming tickets or modifying slots.

`producer_candidate` is invoked at most once per public producer invocation. Internal retries after a stale candidate do not invoke it again.

## Producer progress

A producer stalled at `producer_candidate` must not prevent another producer from acquiring otherwise available capacity.

A producer stalled after ownership at `producer_reserved` must not prevent another producer from acquiring a later independent range when sufficient reusable capacity exists.

Acquiring that range is not the whole requirement. The later producer must also finish its own operation and return while the earlier range is still unpublished.

Completion and consumer visibility are separate events. A producer whose payload work is done returns without waiting for any earlier range; the earlier unpublished range still gates what consumers may observe.

No mutex, reservation lock, ticket lock, or equivalent mechanism may be held across either hook if doing so prevents this required progress.

## Atomic batch publication

Ownership and consumer visibility are separate events.

After ownership, the producer invokes:

```text
HookPoint::producer_reserved
```

before any value from that range is consumer-visible.

No value from a producer batch may become observable until every payload in that batch has been written and the complete range has been published.

If producer range A logically precedes producer range B, consumers must not observe B while any ticket in A remains unpublished, even if B finishes its private payload work first.

After the complete range becomes eligible for ordered consumer visibility, the producer invokes:

```text
HookPoint::producer_published
```

Successful single and batch pushes form one logical FIFO producer stream.

## Batch pop

`try_pop_batch(count)` accepts `count` from `1` through `capacity`; otherwise it throws `std::invalid_argument`.

It returns `std::nullopt` unless it obtains ownership of `count` consecutive logical values beginning at the current available consumer frontier.

A successful pop owns the complete requested logical range atomically.

A failed pop:

- consumes no consumer tickets;
- releases no slots;
- changes no payload or slot state.

Returned values are in logical FIFO order.

## Consumer candidate and ownership

Before consumer ownership is acquired, an invocation may observe that its requested consecutive logical values are currently published and eligible.

The first time an invocation observes such a complete eligible range, it invokes:

```text
HookPoint::consumer_candidate
```

with that observed candidate range.

At `consumer_candidate`:

- the invocation owns no consumer ticket;
- no consumer ticket has been consumed;
- no slot has been released;
- another consumer may acquire the same candidate range while the hook is blocked.

Returning from `consumer_candidate` does not guarantee ownership.

The invocation must revalidate before acquiring the consumer range.

If another consumer acquired the candidate first, the stalled invocation may subsequently acquire a later eligible range if enough published values remain. Otherwise it may return `std::nullopt`.

`consumer_candidate` is invoked at most once per public consumer invocation. Internal retries after a stale candidate do not invoke it again.

## Consumer progress

After a consumer owns a range, it invokes:

```text
HookPoint::consumer_reserved
```

before releasing any physical slot from that range.

A consumer stalled at `consumer_candidate` must not prevent another consumer from acquiring otherwise available published values.

A consumer stalled after ownership at `consumer_reserved` must not prevent another consumer from acquiring a later independently published range, nor from finishing and returning it.

Completion order of concurrently owned consumer ranges does not have to match logical ticket order, but every logical value is owned by exactly one consumer.

## Full, empty, and reuse

At most `capacity` logical values may be owned by producers, published, or owned by consumers without having been released for reuse.

Producer capacity calculations include ranges already owned but not yet published.

A physical slot becomes reusable only after the consumer owning its previous logical value has obtained that payload and released the slot for its next logical cycle.

Repeated reuse must remain correct across physical wraparound and arbitrary ticket values.

Full and empty decisions must use defined modular arithmetic. Signed overflow is not valid synchronization logic.

## Publication and memory visibility

Payload storage is non-atomic.

For every successful producer operation:

- all payload writes happen-before the corresponding range becomes consumer-visible;
- consumers acquiring that published range observe those writes.

A producer must never overwrite a physical slot before its prior consumer releases it.

A consumer must obtain the payload before releasing that slot for reuse.

## Close

`close()` is thread-safe and idempotent.

Close races with producer ownership, not with invocation start.

If a producer is paused at `producer_candidate`, it owns nothing. A concurrent `close()` may complete immediately. When that producer resumes, it must observe closure before acquiring ownership and return `false`.

If a producer has already completed its ownership transition and reached:

```text
HookPoint::producer_reserved
```

a later `close()` does not revoke that ownership.

Therefore:

- candidate before close does not guarantee success;
- reservation before close does guarantee that the owned producer operation may finish;
- `close()` must not wait for a producer blocked inside `producer_candidate` or `producer_reserved`.

After close:

- no new producer ownership may be acquired;
- already-owned producers may finish;
- successfully published values remain drainable;
- consumers continue until the stream is drained;
- once closed and drained, consumer operations return empty results.

`closed()` reports whether closure has been published.

## Observation hooks

The optional hook receives:

```cpp
HookPoint point,
Ticket first_ticket,
std::size_t count
```

The hook points are:

```text
HookPoint::producer_candidate
HookPoint::producer_reserved
HookPoint::producer_published
HookPoint::consumer_candidate
HookPoint::consumer_reserved
HookPoint::consumer_released
```

For single-item operations, `count == 1`.

Candidate hooks describe observed eligibility before ownership. They may occur even when the invocation later fails.

Reserved, published, and released hooks occur only after the corresponding successful lifecycle transition.

For one public invocation:

- each candidate hook is invoked at most once;
- `producer_reserved` and `producer_published` are each invoked exactly once for a successful producer operation;
- `consumer_reserved` and `consumer_released` are each invoked exactly once for a successful consumer operation.

Hook code may block for an arbitrary duration.

The implementation must not hold synchronization across a hook in a way that violates the producer, consumer, or close progress requirements.

## Exact delivery

Across mixed single-item and batch operations:

- every successful producer contributes exactly its input values;
- values participate in one logical producer-ticket order;
- each logical value is returned at most once;
- no value may be fabricated or corrupted;
- failed producer batches contribute nothing;
- failed consumer batches consume nothing.

After producers stop, the ring is closed, and all published values are drained, the multiset of returned distinct test values must exactly equal the multiset supplied by successful producer operations.

## Public concurrency

All public methods may be called concurrently unless explicitly stated otherwise.

The implementation must not rely on undefined behavior for any valid capacity, batch size, ticket value, wraparound, or schedule covered by this contract.
