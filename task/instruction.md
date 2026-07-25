You are auditing an ECDSA signing service whose random number generator is
suspected to be faulty. The service signs with the standard secp256k1 curve
(the usual SEC 2 parameters; call the group order n and the base point G).

The file `/app/data/signatures.json` holds the public evidence you collected. Its
fields are:

- `curve`: always `"secp256k1"`.
- `public_key`: the signer's long-term public key Q, given as hex `x` and `y`
  affine coordinates. Q = d·G, where d is the private key you must recover.
- `nonce_window_bits`: the integer 248 (see the nonce fact below).
- `signatures`: a list of 40 signatures. Each entry has hex integers
  `h`, `r`, `s`. For every entry, the signer used a per-signature secret nonce k
  and the values satisfy the textbook ECDSA relation

      r = (k · G).x  mod n           s = k⁻¹ · (h + r · d)  mod n

  where `h` is the message hash already reduced mod n (use it verbatim), and
  `r`, `s` are as given. No low-s normalization or extra hashing is applied.

The RNG fault is this: instead of ranging over the whole scalar field, the nonces
are confined to a narrow window whose position is fixed but unknown. Concretely,
there is a single integer A, the same for every signature in the file, with
1 ≤ A and A + 2²⁴⁸ ≤ n, such that every nonce satisfies

    A ≤ k < A + 2²⁴⁸

You are not told A, and it is not a small number or a round one — treat it as an
arbitrary value of the same magnitude as n. Nothing else about the nonces is
known: the offsets k − A vary freely across the window.

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
