import { MapContainer, Marker, Popup, TileLayer } from 'react-leaflet'
import L from 'leaflet'
import markerIcon from 'leaflet/dist/images/marker-icon.png'
import markerShadow from 'leaflet/dist/images/marker-shadow.png'
import 'leaflet/dist/leaflet.css'
import type { LocationEntry } from '../types'

const icon = L.icon({
  iconUrl: markerIcon,
  shadowUrl: markerShadow,
  iconSize: [25, 41],
  iconAnchor: [12, 41],
})

export function LocationMap({ locations }: { locations: LocationEntry[] }) {
  if (locations.length === 0) {
    return <p className="muted">まだ誰も位置情報を共有していません。</p>
  }

  const center: [number, number] = [locations[0].latitude, locations[0].longitude]

  return (
    <div style={{ height: 240, borderRadius: 14, overflow: 'hidden', marginBottom: 12 }}>
      <MapContainer center={center} zoom={14} style={{ height: '100%', width: '100%' }}>
        <TileLayer
          attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
          url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
        />
        {locations.map((loc) => (
          <Marker key={loc.user_id} position={[loc.latitude, loc.longitude]} icon={icon}>
            <Popup>
              {loc.display_name}（{loc.minutes_ago}分前）
            </Popup>
          </Marker>
        ))}
      </MapContainer>
    </div>
  )
}
