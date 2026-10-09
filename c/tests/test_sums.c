/* PK11 / C14: the rows of a sha256sum file: a name with trailing white
 * space (a tab or spaces, then CRLF) still matches. */
#include "otc_test.h"
#include "otc_internal.h"

int main(void)
{
    char *dir = test_tmpdir(), *path, hex[65], row[256];
    otc_error err;
    otc_error_init(&err);
    test_write(dir, "OTC_20990101.jsonl", "{}\n");
    path = test_join(dir, "OTC_20990101.jsonl");
    otc__sha256_file(path, hex);
    snprintf(row, sizeof row, "%s  OTC_20990101.jsonl\t\r\n", hex);
    test_write(dir, "OTC_20990101.sha256", row);
    CHECK_STATUS(otc_verify_file(path, NULL, &err), OTC_OK);
    snprintf(row, sizeof row, "%s *OTC_20990101.jsonl \t \n", hex);
    test_write(dir, "OTC_20990101.sha256", row);
    CHECK_STATUS(otc_verify_file(path, NULL, &err), OTC_OK);
    free(path);
    free(dir);
    return test_done("test_sums");
}
