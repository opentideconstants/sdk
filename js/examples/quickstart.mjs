// The quickstart (README). Set OPENTIDECONSTANTS_BASE_URL to use a mirror or the conformance fixture
// server; by default it reads https://data.opentideconstants.org/.
import { OpenTideConstants } from "opentideconstants";

const otc = await OpenTideConstants.open();
console.log(`release ${otc.release.datestamp} (${otc.loadedFrom}), ${otc.release.stationCount} stations`);

const noaaId = process.argv[2] ?? "9414290";
const station = otc.stationByAlias("noaa", noaaId);
if (station) {
    const m2 = station.recommendedSet?.constituent("M2");
    console.log(`${station.station_id} ${station.name}: M2 amplitude ${m2?.amplitude_m} m, phase ${m2?.phase_deg} deg`);
    console.log(otc.near({ lat: station.lat, lon: station.lon, radiusKm: 30 }).map((n) => `${n.station.name} ${n.distance_km.toFixed(1)} km`).join("; "));
    console.log(otc.attribution([station]));
} else {
    console.log(`no station with NOAA id ${noaaId}`);
}
otc.close();
