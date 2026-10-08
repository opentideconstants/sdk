/**
 * OpenTideConstants: read-only, typed access to OpenTideConstants releases (SDK spec 4).
 *
 * ```ts
 * import { OpenTideConstants } from "opentideconstants";
 * const otc = await OpenTideConstants.open();
 * const m2 = otc.stationByAlias("noaa", "9414290")?.recommendedSet?.constituent("M2");
 * ```
 */
export { OpenTideConstants } from "./client.js";
export { Release, Station, ConstantSet } from "./release.js";
export {
    OpenTideConstantsError, NetworkError, ReleaseNotFoundError, OfflineError, ChecksumError, UnsupportedFormatError,
    InvalidReleaseError, StationNotFoundError, StationRemovedError, PinnedReleaseError, CacheError, FileExistsError,
    UnsupportedError, FileError, InvalidArgumentError,
} from "./errors.js";
export type { ErrorCode } from "./errors.js";
export { VERSION, SUPPORTED_FORMAT_MAJORS, DEFAULT_BASE_URL, CACHE_LAYOUT_VERSION } from "./constants.js";
export type { JsonObject, Json } from "./json.js";
export type * from "./types.js";
