/* Ordered harmonic sums and the frozen adaptive event search. */
#include "otc_internal.h"
#include <float.h>

static double number_or(const cJSON *obj, const char *key, double fallback)
{
    const cJSON *value = otc__jget(obj, key);
    return cJSON_IsNumber(value) ? value->valuedouble : fallback;
}

otc_status otc__sum_init(otc__sum *sum, const otc_astro_tab *table, const cJSON *constituents, const char *amplitude, const char *phase, double mean, double multiplier, double shift)
{
    const cJSON *c, *row;
    otc_status st;
    size_t i = 0;
    memset(sum, 0, sizeof *sum);
    sum->table = table; sum->mean = mean;
    sum->n = (size_t)cJSON_GetArraySize(constituents);
    if (sum->n > SIZE_MAX / sizeof *sum->terms) return OTC_E_NOMEM;
    if (sum->n && !(sum->terms = calloc(sum->n, sizeof *sum->terms))) return OTC_E_NOMEM;
    cJSON_ArrayForEach(c, constituents) {
        st = otc__astro_row(table, otc__jstr(c, "name"), &row);
        if (st != OTC_OK) { otc__sum_clear(sum); return st; }
        sum->terms[i].row = row;
        sum->terms[i].speed = otc__jnum(row, "speed_deg_per_hour");
        sum->terms[i].amplitude = multiplier * number_or(c, amplitude, 0.0);
        sum->terms[i].phase = otc__angle(number_or(c, phase, 0.0) + sum->terms[i].speed * shift);
        i++;
    }
    return OTC_OK;
}
void otc__sum_clear(otc__sum *sum) { free(sum->terms); memset(sum, 0, sizeof *sum); }

static otc_status prepare(otc__sum *sum, int year)
{
    size_t i;
    int index;
    otc_status st;
    if (sum->year == year && year) return OTC_OK;
    st = otc__astro_index(sum->table, year, &index);
    if (st != OTC_OK) return st;
    sum->origin = (double)otc__year_start(year);
    for (i = 0; i < sum->n; i++) {
        otc__term *t = &sum->terms[i];
        t->scaled = cJSON_GetArrayItem(otc__jget(t->row, "f"), index)->valuedouble * t->amplitude;
        t->argument = cJSON_GetArrayItem(otc__jget(t->row, "v0u_deg"), index)->valuedouble - t->phase;
        t->omega = t->speed * OTC__RAD;
    }
    sum->year = year;
    return OTC_OK;
}

otc_status otc__sum_prepare(otc__sum *sum, int year)
{
    return prepare(sum, year);
}

otc_status otc__sum_value(otc__sum *sum, double seconds, int year, int derivative, double *out)
{
    size_t i;
    double value = 0.0, delta, phase;
    otc_status st = prepare(sum, year ? year : otc__year(seconds));
    if (st != OTC_OK) return st;
    delta = (seconds - sum->origin) / 3600.0;
    for (i = 0; i < sum->n; i++) {
        const otc__term *t = &sum->terms[i];
        phase = otc__angle(t->speed * delta + t->argument) * OTC__RAD;
        value += derivative ? -t->scaled * t->omega * sin(phase) : t->scaled * cos(phase);
    }
    *out = derivative ? value : value + sum->mean;
    return OTC_OK;
}

static double bound(otc__sum *sum, int derivative)
{
    size_t i;
    double result = 0.0;
    for (i = 0; i < sum->n; i++) {
        const otc__term *t = &sum->terms[i];
        result += fabs(t->scaled) * (derivative ? t->omega * t->omega : t->omega);
    }
    return result;
}
static double error_bound(otc__sum *sum, double a, double b, int derivative)
{
    size_t i;
    double result = 0.0, delta = fmax(fabs(a - sum->origin), fabs(b - sum->origin)) / 3600.0;
    for (i = 0; i < sum->n; i++) {
        const otc__term *t = &sum->terms[i];
        result += fabs(t->scaled) * (derivative ? t->omega : 1.0) * (fabs(t->omega * delta) + 2.0 * 3.14159265358979323846);
    }
    return 4.0 * DBL_EPSILON * result;
}
static otc_status append(otc__events *events, double t, int kind, double value)
{
    if (events->n == events->cap) {
        size_t cap = events->cap ? events->cap * 2 : 32;
        otc__event *items;
        if (cap < events->cap || cap > SIZE_MAX / sizeof *items) return OTC_E_NOMEM;
        items = realloc(events->items, cap * sizeof *items);
        if (!items) return OTC_E_NOMEM;
        events->items = items; events->cap = cap;
    }
    events->items[events->n].t = t; events->items[events->n].kind = kind;
    events->items[events->n].value = value; events->items[events->n].sequence = events->n;
    events->n++;
    return OTC_OK;
}
static otc_status subdivide(otc__sum *sum, int year, double bounded, int slack, otc__events *roots, double a, double b, double fa, double fb, int depth)
{
    double middle, fm, root, value;
    int falling, rising, derivative = !slack;
    otc_status st;
    double margin = bounded * ((b - a) / 3600.0) * (1.0 + 1e-9) + 2.0 * error_bound(sum, a, b, derivative) + 1e-12 * fmax(1.0, bounded);
    if (fabs(fa) + fabs(fb) > margin) return OTC_OK;
    if (depth < 9) {
        middle = (a + b) / 2.0;
        st = otc__sum_value(sum, middle, year, derivative, &fm);
        if (st != OTC_OK) return st;
        st = subdivide(sum, year, bounded, slack, roots, a, middle, fa, fm, depth + 1);
        return st == OTC_OK ? subdivide(sum, year, bounded, slack, roots, middle, b, fm, fb, depth + 1) : st;
    }
    falling = fa > 0 && fb <= 0; rising = fa < 0 && fb >= 0;
    if (!falling && !rising) return OTC_OK;
    while (b - a > 0.01) {
        middle = (a + b) / 2.0;
        st = otc__sum_value(sum, middle, year, derivative, &fm);
        if (st != OTC_OK) return st;
        if ((falling && fm > 0) || (rising && fm < 0)) a = middle;
        else b = middle;
    }
    root = (a + b) / 2.0; value = 0;
    if (!slack && (st = otc__sum_value(sum, root, year, 0, &value)) != OTC_OK) return st;
    return append(roots, root, slack ? (falling ? OTC_CURRENT_EVENT_TYPE_SLACK_BEFORE_EBB : OTC_CURRENT_EVENT_TYPE_SLACK_BEFORE_FLOOD) : (falling ? OTC_EXTREME_TYPE_HIGH : OTC_EXTREME_TYPE_LOW), value);
}
static int order(const void *aa, const void *bb)
{
    const otc__event *a = aa, *b = bb;
    if (a->t < b->t) return -1;
    if (a->t > b->t) return 1;
    return a->sequence < b->sequence ? -1 : a->sequence > b->sequence;
}
static size_t survivor(const otc__event *items, size_t n, int slack)
{
    size_t i, chosen = 0;
    int high;
    if (!(n % 2)) return SIZE_MAX;
    if (slack) return 2 * ((n - 1) / 4);
    high = items[0].kind == OTC_EXTREME_TYPE_HIGH;
    for (i = 1; i < n; i++) if (items[i].kind == items[0].kind &&
        ((high && (items[i].value > items[chosen].value || (items[i].value == items[chosen].value && items[i].t < items[chosen].t))) ||
         (!high && (items[i].value < items[chosen].value || (items[i].value == items[chosen].value && items[i].t < items[chosen].t))))) chosen = i;
    return chosen;
}
void otc__events_clear(otc__events *events) { free(events->items); memset(events, 0, sizeof *events); }

otc_status otc__events_find_unrounded(otc__sum *sum, double start, double stop, int slack, otc__events *out)
{
    double first, last, point, fa, fb, bounded;
    int year, index, first_year, last_year;
    size_t i, left, right, n, selected, written = 0;
    otc_status st = OTC_OK;
    memset(out, 0, sizeof *out);
    if (start == stop) return OTC_OK;
    first = floor(start / 360.0) * 360.0 - 3600.0;
    last = ceil((stop + 3600.0 - first) / 360.0) * 360.0 + first;
    for (point = first; point <= last; point += 360.0) {
        st = otc__astro_index(sum->table, otc__year(point), &index);
        if (st != OTC_OK) goto fail;
    }
    for (point = first; point < last; point += 360.0) {
        year = otc__year(point);
        st = prepare(sum, year);
        if (st != OTC_OK) goto fail;
        bounded = bound(sum, !slack);
        st = otc__sum_value(sum, point, year, !slack, &fa);
        if (st != OTC_OK) goto fail;
        st = otc__sum_value(sum, point + 360.0, year, !slack, &fb);
        if (st != OTC_OK) goto fail;
        st = subdivide(sum, year, bounded, slack, out, point, point + 360.0, fa, fb, 0);
        if (st != OTC_OK) goto fail;
    }
    first_year = otc__year(first); last_year = otc__year(last);
    for (year = first_year + 1; year <= last_year; year++) {
        point = (double)otc__year_start(year);
        if (!(first < point && point < last)) continue;
        st = otc__sum_value(sum, point, year - 1, !slack, &fa);
        if (st != OTC_OK) goto fail;
        st = otc__sum_value(sum, point, year, !slack, &fb);
        if (st != OTC_OK) goto fail;
        if (fa == 0 || fb == 0 || (fa > 0) == (fb > 0)) continue;
        left = right = SIZE_MAX;
        for (i = 0; i < out->n; i++) {
            if (out->items[i].t <= point) left = i;
            else if (right == SIZE_MAX) right = i;
        }
        if (left != SIZE_MAX && right != SIZE_MAX && out->items[right].t - out->items[left].t < 3600.0) {
            size_t loser = right;
            if (!slack) {
                otc__event candidates[3] = {out->items[left], out->items[right], out->items[left]};
                selected = survivor(candidates, 3, 0);
                loser = selected == 1 ? left : right;
            }
            memmove(out->items + loser, out->items + loser + 1, (out->n - loser - 1) * sizeof *out->items); out->n--;
        } else {
            double value = 0;
            if (!slack && (st = otc__sum_value(sum, point, year, 0, &value)) != OTC_OK) goto fail;
            st = append(out, point, slack ? (fb > 0 ? OTC_CURRENT_EVENT_TYPE_SLACK_BEFORE_FLOOD : OTC_CURRENT_EVENT_TYPE_SLACK_BEFORE_EBB) : (fa > 0 ? OTC_EXTREME_TYPE_HIGH : OTC_EXTREME_TYPE_LOW), value);
            if (st != OTC_OK) goto fail;
        }
        qsort(out->items, out->n, sizeof *out->items, order);
    }
    for (i = 0; i < out->n; i += n) {
        for (n = 1; i + n < out->n && out->items[i + n].t - out->items[i + n - 1].t < 1.0; n++) {}
        selected = survivor(out->items + i, n, slack);
        if (selected != SIZE_MAX)
            out->items[written++] = out->items[i + selected];
    }
    out->n = written;
    return OTC_OK;
fail:
    otc__events_clear(out);
    return st;
}

otc_status otc__events_find(otc__sum *sum, double start, double stop, int slack, otc__events *out)
{
    size_t i, written = 0;
    otc_status st = otc__events_find_unrounded(sum, start, stop, slack, out);
    if (st != OTC_OK) return st;
    for (i = 0; i < out->n; i++)
        if (start <= floor(out->items[i].t + 0.5) && floor(out->items[i].t + 0.5) < stop)
            out->items[written++] = out->items[i];
    out->n = written;
    return OTC_OK;
}
