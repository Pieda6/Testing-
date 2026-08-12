Repair `/app/src/mpmc_ring.cpp` so the bounded multi-producer/multi-consumer ring satisfies every normative requirement in `/app/MPMC_SPEC.md`. Do not modify `/app/include/mpmc_ring.h` or the specification.

The ring supports concurrent single-item and atomic batch pushes and pops. Correctness includes all-or-nothing batch failure, logical FIFO ordering, publication visibility, safe physical-slot reuse, modular `std::uint64_t` ticket arithmetic, close-and-drain behavior, and exact-once delivery.

The observation hooks distinguish eligibility from ownership. At `producer_candidate` or `consumer_candidate`, the invocation has observed an eligible logical range but owns nothing: no ticket has been consumed and no slot has been reserved or released. Hook code may block. While a candidate hook is blocked, another operation may acquire that same candidate range. When the stalled invocation resumes, it must revalidate current state and may acquire a later eligible range rather than incorrectly using stale state or failing solely because another operation overtook it. A candidate hook occurs at most once per public invocation.

`close()` may win while a producer is blocked at `producer_candidate`; that producer must then fail without acquiring ownership. By contrast, an operation that has reached `producer_reserved` already owns its complete range, and a later close must not revoke it. `close()` must not wait for a thread blocked in either producer hook.

A producer stalled after ownership must not prevent another producer from reserving later independent capacity, nor from finishing and returning while that earlier range is still unpublished: completing an operation and becoming visible to consumers are separate events. A consumer stalled before or after ownership must not prevent another consumer from acquiring otherwise available published values and returning them. Synchronization held across hooks must not violate these progress requirements.

Producer batches own contiguous logical ticket ranges. Consumers must never observe a partial producer batch or bypass an unpublished earlier logical range even if a later producer finishes its payload work first. Consumer batches likewise acquire their complete requested range or consume nothing. Failed operations must not partially advance tickets or mutate slot lifecycle state.

The implementation must remain correct when logical ranges cross the physical ring boundary, the signed 64-bit boundary, or unsigned ticket wraparound. Preserve the supplied fixed-capacity storage model and public API.

The only graded artifact is the repaired regular file `/app/src/mpmc_ring.cpp`. A missing artifact scores zero.
