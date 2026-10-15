/* Local time loads the native TZif rules only on demand, without process TZ. */
#if defined(OTC_WITH_LOCALTIME) && OTC_WITH_LOCALTIME && !defined(_WIN32) && !defined(__FreeBSD__)
#define THREAD_SAFE 1
#define NETBSD_INSPIRED 1
#define STD_INSPIRED 0
#define HAVE_TZNAME 0
#define USG_COMPAT 0
#define ALTZONE 0
#include "otc_tz_rename.h" /* IWYU pragma: keep; namespaces every external tzcode symbol */
/* With HAVE_TZNAME=0, upstream update_tzname_etc deliberately has two
 * unused arguments. Keep upstream bytes intact and scope the exemption. */
#if defined(__GNUC__)
#pragma GCC diagnostic push
#pragma GCC diagnostic ignored "-Wunused-parameter"
#endif
#include "../vendor/tzcode/localtime.c"
#if defined(__GNUC__)
#pragma GCC diagnostic pop
#endif

#endif
#include "otc_internal.h"
#include <errno.h>
#if defined(OTC_WITH_LOCALTIME) && OTC_WITH_LOCALTIME && !defined(_WIN32) && !defined(__FreeBSD__)
#include <dirent.h>
#include <sys/stat.h>
#include <unistd.h>
struct otc_tz { timezone_t rules; };

static char *tz_path(const char *directory, const char *name)
{
    char *prefix = otc__join(directory, "/"), *path;
    if (!prefix) return NULL;
    path = otc__join(prefix, name);
    free(prefix);
    return path;
}
static int zone_valid(const char *zone)

{
    size_t i, n;
    if (!zone || !(n=strlen(zone)) || n>255 || zone[0]=='/' || zone[n-1]=='/' || !strncmp(zone,"posix/",6) || !strncmp(zone,"right/",6) || !strcmp(zone,"posixrules") || !strcmp(zone,"localtime") || !strcmp(zone,"Factory")) return 0;
    for (i=0;i<n;i++) {
        unsigned char c=(unsigned char)zone[i];
        if (c=='/') { if (i && zone[i-1]=='/') return 0; }
        else if (!((c>='A' && c<='Z') || (c>='a' && c<='z') || (c>='0' && c<='9') || c=='_' || c=='+' || c=='-')) return 0;
    }
    return 1;
}

otc_status otc_tz_open(const char *zone, otc_tz **out)
{
    const char *directory=getenv("TZDIR");
    DIR *dir;
    struct stat statbuf;
    char *path, magic[4];
    FILE *file;
    otc_tz *tz;
    if (out) *out=NULL;
    if (!out) return OTC_E_INVALID_ARGUMENT;
    if (!directory || !*directory) directory=TZDIR;
    dir=opendir(directory);
    if (!dir) return OTC_E_LOCAL_TIME_UNAVAILABLE;
    closedir(dir);
    if (!zone_valid(zone)) return OTC_E_UNKNOWN_TIME_ZONE;
    path=tz_path(directory,zone);
    if (!path) return OTC_E_NOMEM;
    /* A relative TZDIR is resolved without changing the process directory. */
    if (path[0]!='/') {
        char *cwd=getcwd(NULL,0), *absolute;
        if (!cwd) { free(path); return OTC_E_LOCAL_TIME_UNAVAILABLE; }
        absolute=tz_path(cwd,path); free(cwd); free(path); path=absolute;
        if (!path) return OTC_E_NOMEM;
    }
    if (stat(path,&statbuf) || !S_ISREG(statbuf.st_mode) || !(file=fopen(path,"rb"))) { free(path); return OTC_E_UNKNOWN_TIME_ZONE; }
    if (fread(magic,1,4,file)!=4 || memcmp(magic,"TZif",4)) { fclose(file); free(path); return OTC_E_UNKNOWN_TIME_ZONE; }
    fclose(file);
    tz=calloc(1,sizeof *tz);
    if (!tz) { free(path); return OTC_E_NOMEM; }
    errno=0; tz->rules=otc__tzalloc(path); free(path);
    if (!tz->rules) { free(tz); return errno==ENOMEM ? OTC_E_NOMEM : OTC_E_UNKNOWN_TIME_ZONE; }
    *out=tz; return OTC_OK;
}

otc_status otc_tz_local(const otc_tz *tz, int64_t t, otc_local_t *out)
{
    time_t native=(time_t)t;
    struct tm local;
    long offset;
    char sign, text[96];
    if (out) memset(out,0,sizeof *out);
    if (!tz || !out || (int64_t)native!=t) return OTC_E_INVALID_ARGUMENT;
    if (!otc__localtime_rz(tz->rules,&native,&local)) return OTC_E_INVALID_ARGUMENT;
    offset=local.TM_GMTOFF;
    if (offset<INT32_MIN || offset>INT32_MAX || local.tm_year < -1899 || local.tm_year > 8099) return OTC_E_INVALID_ARGUMENT;
    out->t=t; out->utc_offset_s=(int32_t)offset;
    sign=offset<0 ? '-' : '+'; if (offset<0) offset=-offset;
    if (offset%60) snprintf(text,sizeof text,"%04d-%02d-%02dT%02d:%02d:%02d%c%02ld:%02ld:%02ld",local.tm_year+1900,local.tm_mon+1,local.tm_mday,local.tm_hour,local.tm_min,local.tm_sec,sign,offset/3600,offset/60%60,offset%60);
    else snprintf(text,sizeof text,"%04d-%02d-%02dT%02d:%02d:%02d%c%02ld:%02ld",local.tm_year+1900,local.tm_mon+1,local.tm_mday,local.tm_hour,local.tm_min,local.tm_sec,sign,offset/3600,offset/60%60);
    if (strlen(text)>=sizeof out->local_time) { memset(out,0,sizeof *out); return OTC_E_INVALID_ARGUMENT; }
    memcpy(out->local_time,text,strlen(text)+1);
    return OTC_OK;
}
void otc_tz_close(otc_tz *tz) { if (tz) { otc__tzfree(tz->rules); free(tz); } }
otc_status otc_tz_version(char *buf, size_t len, size_t *needed)
{
    const char *directory=getenv("TZDIR");
    char *path, line[256], version[128];
    FILE *file;
    if (needed) *needed=0;
    if (buf && len) buf[0]='\0';
    if (!buf && len) return OTC_E_INVALID_ARGUMENT;
    if (!directory || !*directory) directory=TZDIR;
    path=tz_path(directory,"tzdata.zi");
    if (!path) return OTC_E_NOMEM;
    file=fopen(path,"rb"); free(path);
    if (!file) return OTC_E_NOT_FOUND;
    if (!fgets(line,sizeof line,file) || sscanf(line,"# version %127s",version)!=1) { fclose(file); return OTC_E_NOT_FOUND; }
    fclose(file);
    return otc__copy_str(version,buf,len,needed);
}
#else
struct otc_tz { int unused; };
otc_status otc_tz_open(const char *zone, otc_tz **out) { (void)zone; if (out) *out=NULL; return OTC_E_NOT_BUILT; }
otc_status otc_tz_local(const otc_tz *tz, int64_t t, otc_local_t *out) { (void)tz; (void)t; if (out) memset(out,0,sizeof *out); return OTC_E_NOT_BUILT; }
void otc_tz_close(otc_tz *tz) { (void)tz; }
otc_status otc_tz_version(char *buf, size_t len, size_t *needed) { if (needed) *needed=0; if (buf && len) buf[0]='\0'; return OTC_E_NOT_BUILT; }
#endif
