import { useEffect, useState } from 'react'
import comuniUrl from '../../assets/comuni.geojson?url'

/** The comuni of the ATS from ISTAT boundaries (delivery plan 1.11, D16): local, no basemap. */
export type Comune = { istat: string; name: string; asst: string; d: string }
export type Geo = { comuni: Comune[]; width: number; height: number }

type Feature = {
  properties: { comune_istat: string; name: string; asst_id: string }
  geometry: { coordinates: number[][][][] } // MultiPolygon, lon/lat
}

export const GEO_WIDTH = 900
const PAD = 10

/** Equirectangular projection scaled by cos(latitude), as in map-test.html: at 45° N it is close enough. */
function project(features: Feature[]): Geo {
  const points = features.flatMap((f) => f.geometry.coordinates.flat(2))
  const lons = points.map((p) => p[0])
  const lats = points.map((p) => p[1])
  const [minLon, maxLon, minLat, maxLat] = [Math.min(...lons), Math.max(...lons), Math.min(...lats), Math.max(...lats)]
  const k = Math.cos((((minLat + maxLat) / 2) * Math.PI) / 180)
  const scale = (GEO_WIDTH - 2 * PAD) / ((maxLon - minLon) * k)
  const xy = ([lon, lat]: number[]) => `${(PAD + (lon - minLon) * k * scale).toFixed(1)},${(PAD + (maxLat - lat) * scale).toFixed(1)}`
  const comuni = features.map((f) => ({
    istat: f.properties.comune_istat,
    name: f.properties.name,
    asst: f.properties.asst_id,
    d: f.geometry.coordinates.flat().map((ring) => `M${ring.map(xy).join('L')}Z`).join(''),
  }))
  return { comuni, width: GEO_WIDTH, height: Math.ceil((maxLat - minLat) * scale) + 2 * PAD }
}

let cache: Promise<Geo> | undefined

/** The projected comuni, loaded once per page. */
export function useGeo(): { geo?: Geo; error?: string } {
  const [state, setState] = useState<{ geo?: Geo; error?: string }>({})
  useEffect(() => {
    let live = true
    cache ??= fetch(comuniUrl)
      .then(async (r) => {
        if (!r.ok) throw new Error(`${r.status}`)
        return project(((await r.json()) as { features: Feature[] }).features)
      })
      .catch((e: unknown) => {
        cache = undefined // try again on the next visit
        throw e
      })
    cache.then((geo) => live && setState({ geo })).catch((e: unknown) => live && setState({ error: String(e) }))
    return () => {
      live = false
    }
  }, [])
  return state
}
