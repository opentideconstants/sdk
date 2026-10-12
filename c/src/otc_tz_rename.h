/* Every external tzcode function is namespaced; libc remains untouched. */
#ifndef OTC_TZ_RENAME_H
#define OTC_TZ_RENAME_H
#define tzset otc__tzset
#define tzalloc otc__tzalloc
#define tzfree otc__tzfree
#define localtime_rz otc__localtime_rz
#define localtime otc__localtime
#define localtime_r otc__localtime_r
#define gmtime otc__gmtime
#define gmtime_r otc__gmtime_r
#define mktime otc__mktime
#define mktime_z otc__mktime_z
#define timegm otc__timegm
#define timeoff otc__timeoff
#endif
