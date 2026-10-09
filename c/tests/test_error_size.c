/* PK20 / C99 (B4-8): the library writes into a caller's otc_error only when
 * its struct_size says it is the size the library knows (set by
 * otc_error_init). A smaller struct (an older caller, or one never
 * initialised) is not written past its end: it is left alone. */
#include "otc_test.h"

#include <stddef.h>

int main(void)
{
    unsigned char buf[sizeof(otc_error) + 64];
    otc_error *e = (otc_error *)(void *)buf;
    otc_open_options oo;
    otc_release *rel = NULL;
    size_t i, small = offsetof(otc_error, message);   /* "an older, smaller otc_error" */
    int over = 0;
    memset(buf, 0xA5, sizeof buf);
    e->struct_size = small;
    otc_open_options_init(&oo);
    oo.error = e;
    CHECK_STATUS(otc_open_file("/no/such/OTC_20990101.jsonl", &oo, &rel), OTC_E_IO);
    for (i = small; i < sizeof buf; i++) if (buf[i] != 0xA5) over = 1;
    CHECK(!over);
    if (over) fprintf(stderr, "the library wrote past the caller's struct_size (%lu bytes)\n", (unsigned long)small);
    CHECK(e->struct_size == small);
    memset(buf, 0xA5, sizeof buf);
    e->struct_size = small;
    CHECK_STATUS(otc_verify_file("/no/such/file.jsonl", "/no/such/file.sha256", e), OTC_E_IO);
    over = 0;
    for (i = small; i < sizeof buf; i++) if (buf[i] != 0xA5) over = 1;
    CHECK(!over);
    /* a full-size one still gets the detail */
    otc_error_init(e);
    CHECK_STATUS(otc_open_file("/no/such/OTC_20990101.jsonl", &oo, &rel), OTC_E_IO);
    CHECK(e->status == OTC_E_IO && e->message[0]);
    return test_done("test_error_size");
}
