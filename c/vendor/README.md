# Vendored code

These files are copied from upstream byte for byte. Do not edit them. To update one, copy the new upstream files, update this table, and run the conformance suite again. The SHA-256 values are of the files in this directory.

| Directory | Upstream | Version | Licence | File | SHA-256 |
|---|---|---|---|---|---|
| `cjson/` | https://github.com/DaveGamble/cJSON | tag `v1.7.19` (commit `c859b25da02955fef659d658b8f324b5cde87be3`) | MIT (`cjson/LICENSE`) | `cJSON.c` | `298581a04a36c0165da4b0aade235c23088cb2faa58651d720ea2f3706ed0b0d` |
| | | | | `cJSON.h` | `25b0145150d500498e4d209cec69c18c42cf818bffcc54690be3b895a2a16dee` |
| | | | | `LICENSE` | `a36dda207c36db5818729c54e7ad4e8b0c6fba847491ba64f372c1a2037b6d5c` |
| `sha256/` | https://github.com/amosnier/sha-2 | commit `565f65009bdd98267361b17d50cddd7c9beb3e6c` (no tags upstream) | Unlicense (public-domain dedication) or 0BSD, at the user's option (`sha256/LICENSE.md`) | `sha-256.c` | `7a74437adc78576b8faff060f9573ba88a6da798914f45d263c75b149add3d27` |
| | | | | `sha-256.h` | `c2173d83813a0c29fcc3345ce489766efeadee6a52ca927ecd0f917a120df9fb` |
| | | | | `LICENSE.md` | `506de94a03e23bbc34e32a8b628b56688ac7c33672982388822816887727f1ac` |

Raw URLs: `https://raw.githubusercontent.com/DaveGamble/cJSON/v1.7.19/<file>` and `https://raw.githubusercontent.com/amosnier/sha-2/565f65009bdd98267361b17d50cddd7c9beb3e6c/<file>`.

The library does not use the upstream names directly: `src/otc_cjson_rename.h` and `src/otc_sha256_rename.h` rename every public symbol with an `otc__` prefix, so an application can link its own cJSON next to this library.

Why `amosnier/sha-2` and not `B-Con/crypto-algorithms`: the B-Con `sha256.c` shifts a promoted `unsigned char` left by 24 bits (`data[j] << 24`), which is signed-integer overflow for bytes ≥ 0x80 and fails UBSan. `sha-256.c` casts to `uint32_t` before it shifts.
