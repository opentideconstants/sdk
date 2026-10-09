/* PK20 / C99 (B4-8): the library writes into a caller's otc_error only when
 * its struct_size says it is the size the library knows (set by
 * otc_error_init). A smaller struct (an older caller's) is left alone: no byte
 * after its struct_size is written, also none inside the smaller size. A full
 * one gets the detail, and nothing past its end is written. (A struct never
 * initialised can hold any struct_size, so the library cannot tell it from a
 * full one: initialising it is the caller's part.) */
#include "otc_test.h"

#include <stddef.h>

/* An otc_error with room after it, aligned as an otc_error (a plain byte array
 * cast to otc_error * may be misaligned for its size_t). */
typedef union {
    otc_error e;
    unsigned char b[sizeof(otc_error) + 64];
} padded_error;

/* The first byte from FROM on that is not 0xA5, or -1. */
static long changed_at(const padded_error *p, size_t from)
{
    size_t i;
    for (i = from; i < sizeof p->b; i++)
        if (p->b[i] != 0xA5) return (long)i;
    return -1;
}

int main(void)
{
    padded_error buf;
    otc_error *e = &buf.e;
    otc_open_options oo;
    otc_release *rel = NULL;
    size_t small = offsetof(otc_error, message);   /* "an older, smaller otc_error" */
    long at;
    memset(buf.b, 0xA5, sizeof buf.b);
    e->struct_size = small;
    otc_open_options_init(&oo);
    oo.error = e;
    CHECK_STATUS(otc_open_file("/no/such/OTC_20990101.jsonl", &oo, &rel), OTC_E_IO);
    /* every byte after struct_size, also status, http_status and file[], which lie inside the smaller size */
    at = changed_at(&buf, sizeof e->struct_size);
    if (at >= 0) fprintf(stderr, "otc_open_file wrote byte %ld of a %lu-byte otc_error\n", at, (unsigned long)small);
    CHECK(at < 0);
    CHECK(e->struct_size == small);
    memset(buf.b, 0xA5, sizeof buf.b);
    e->struct_size = small;
    CHECK_STATUS(otc_verify_file("/no/such/file.jsonl", "/no/such/file.sha256", e), OTC_E_IO);
    at = changed_at(&buf, sizeof e->struct_size);
    if (at >= 0) fprintf(stderr, "otc_verify_file wrote byte %ld of a %lu-byte otc_error\n", at, (unsigned long)small);
    CHECK(at < 0);
    CHECK(e->struct_size == small);
    /* a full-size one still gets the detail, and nothing after its end is written */
    memset(buf.b, 0xA5, sizeof buf.b);
    otc_error_init(e);
    CHECK_STATUS(otc_open_file("/no/such/OTC_20990101.jsonl", &oo, &rel), OTC_E_IO);
    CHECK(e->status == OTC_E_IO && e->message[0]);
    at = changed_at(&buf, sizeof(otc_error));
    if (at >= 0) fprintf(stderr, "otc_open_file wrote byte %ld, past the end of a full otc_error\n", at);
    CHECK(at < 0);
    return test_done("test_error_size");
}
