You are auditing an ECDSA signing service whose random number generator is
suspected to be faulty. The service signs with the standard secp256k1 curve
(the usual SEC 2 parameters; call the group order n and the base point G).

The file `/app/data/signatures.json` holds the public evidence you collected. Its
fields are:

- `curve`: always `"secp256k1"`.
- `public_key`: the signer's long-term public key Q, given as hex `x` and `y`
  affine coordinates. Q = d·G, where d is the private key you must recover.
- `session_window_bits`: an object mapping each session id to that session's
  window width exponent (see the nonce fact below). The widths are not all the
  same.
- `signatures`: a list of 44 records. Each record has hex integers `h`, `r`, `s`,
  an integer `session`, and a boolean `s_low_normalized`. For every record the
  signer used a per-signature secret nonce k, and the true values satisfy the
  textbook ECDSA relation

      r = (k · G).x  mod n           s_true = k⁻¹ · (h + r · d)  mod n

  where `h` is the message hash already reduced mod n (use it verbatim) and `r`
  is as given. No extra hashing is applied.

Two recording details matter:

- `s_low_normalized`: the archive that produced this file applied low-s
  normalization to some records. When this flag is `true`, the stored `s` is
  n − s_true rather than s_true itself; when it is `false`, the stored `s` is
  s_true. Recover s_true before using the record.
- `session`: the signing service restarted its RNG between sessions, and this
  field records which session each signature belongs to.

The RNG fault is this: instead of ranging over the whole scalar field, the nonces
of a session are confined to a narrow window whose position is fixed but unknown.
Write W_g for `session_window_bits[g]`. For each session g there is an integer
A_g, the same for every signature of that session, with 1 ≤ A_g and
A_g + 2^(W_g) ≤ n, such that every nonce k of session g satisfies

    A_g ≤ k < A_g + 2^(W_g)

Two things vary from session to session and must be taken from the file, not
assumed: the base A_g and the width W_g.

The A_g are not given to you, and they are neither small nor round — treat each
as an arbitrary value of the same magnitude as n. Different sessions have
different, unrelated bases: knowing one tells you nothing about another. The
widths W_g are given, and they differ between sessions. Nothing else about the
nonces is known; within a window the offsets k − A_g vary freely.

Recover the signer's private key d and write it to `/app/result.json` as a single
JSON object with exactly this shape:

    {"private_key": "<hex>"}

where `<hex>` is d written in hexadecimal (a leading `0x` is optional). Write no
other files.

Your submission is correct when all of the following hold:

1. `/app/result.json` exists and is a JSON object whose `private_key` value is a
   hex string decoding to an integer d with 1 ≤ d < n.
2. The recovered d is the actual private key: d·G equals the public key Q given
   in `signatures.json` (checked by independent scalar multiplication on the
   curve).
