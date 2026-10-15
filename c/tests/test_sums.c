/* PK11 / C14: the rows of a sha256sum file: a name with trailing white
 * space (a tab or spaces, then CRLF; or CRLF alone) still matches. The match
 * is still the whole name and the whole digest: a row whose name has more
 * after it, or whose digest is wrong, does not verify the file. */
#include "otc_test.h"
#include "otc_internal.h"

static char *g_dir, *g_path;

/* Writes ROW (a format with one %s, the digest) as the .sha256 and verifies the file against it. */
static otc_status verify_with(const char *row_fmt, const char *hex)
{
    char row[256];
    otc_error err;
    otc_status st;
    otc_error_init(&err);
    snprintf(row, sizeof row, row_fmt, hex);
    test_write(g_dir, "OTC_20990101.sha256", row);
    st = otc_verify_file(g_path, NULL, &err);
    if (st != OTC_OK) printf("  row \"%s\": %s (%s)\n", row_fmt, otc_status_code(st), err.message);
    return st;
}

int main(void)
{
    char hex[65], wrong[65];
    otc_status st;
    g_dir = test_tmpdir();
    test_write(g_dir, "OTC_20990101.jsonl", "{}\n");
    g_path = test_join(g_dir, "OTC_20990101.jsonl");
    hex[0] = '\0';
    st = otc__sha256_file(g_path, hex);
    if (st != OTC_OK || strlen(hex) != 64) {
        fprintf(stderr, "test_sums: otc__sha256_file gave %s\n", otc_status_code(st));
        return 2;
    }
    memcpy(wrong, hex, sizeof wrong);
    wrong[0] = wrong[0] == '0' ? '1' : '0';
    /* trailing white space after the name, and CRLF */
    CHECK_STATUS(verify_with("%s  OTC_20990101.jsonl\t\r\n", hex), OTC_OK);
    CHECK_STATUS(verify_with("%s *OTC_20990101.jsonl \t \n", hex), OTC_OK);
    CHECK_STATUS(verify_with("%s  OTC_20990101.jsonl\r\n", hex), OTC_OK);
    /* the controls: the same rows with a wrong digest, or a name that only starts the same */
    CHECK_STATUS(verify_with("%s  OTC_20990101.jsonl\t\r\n", wrong), OTC_E_CHECKSUM);
    CHECK_STATUS(verify_with("%s  OTC_20990101.jsonlX\t\r\n", hex), OTC_E_CHECKSUM);
    CHECK_STATUS(verify_with("%s  OTC_20990101.jsonl x\n", hex), OTC_E_CHECKSUM);
    CHECK_STATUS(verify_with("%s  OTC_20990101.json\n", hex), OTC_E_CHECKSUM);
    free(g_path);
    free(g_dir);
    return test_done("test_sums");
}
