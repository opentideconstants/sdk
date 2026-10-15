/* PK13 / C12: the file handle a release keeps open is close-on-exec, so it
 * does not leak into a child process the app starts. */
#include "otc_test.h"

#include <fcntl.h>
#include <sys/stat.h>

int main(void)
{
    char *dir = test_tmpdir(), *path;
    otc_release *rel = NULL;
    struct stat want;
    int fd, found = 0;
    test_write(dir, "OTC_20990101.meta.json", TEST_META("20990101"));
    test_write(dir, "OTC_20990101.jsonl", TEST_STATION("OTC-X-1", "One") "\n");
    path = test_join(dir, "OTC_20990101.jsonl");
    if (stat(path, &want) != 0) { perror(path); return 2; }
    CHECK_STATUS(otc_open_file(path, NULL, &rel), OTC_OK);
    for (fd = 3; fd < 256; fd++) {
        struct stat sb;
        int fl;
        if (fstat(fd, &sb) != 0 || sb.st_ino != want.st_ino || sb.st_dev != want.st_dev) continue;
        found = 1;
        fl = fcntl(fd, F_GETFD);   /* -1 (all bits set) is a failure, not "close-on-exec" */
        CHECK(fl != -1 && (fl & FD_CLOEXEC));
        if (fl == -1) fprintf(stderr, "fcntl(%d, F_GETFD) failed\n", fd);
        else if (!(fl & FD_CLOEXEC)) fprintf(stderr, "fd %d of %s is inherited by child processes\n", fd, path);
    }
    CHECK(found);
    otc_close(rel);
    free(path);
    free(dir);
    return test_done("test_cloexec");
}
