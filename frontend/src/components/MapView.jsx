import { Circle, MapContainer, Polygon, Polyline, TileLayer } from 'react-leaflet'

const floodCoords = [
  [27.94, 84.1],
  [27.85, 84.3],
  [27.74, 84.42],
  [27.7, 84.58],
  [27.62, 84.76],
  [27.54, 84.9],
  [27.5, 85.1],
  [27.58, 85.22],
  [27.7, 85.18],
  [27.82, 85.0],
  [27.92, 84.72],
  [27.98, 84.5],
  [27.96, 84.2],
]

const riverCoords = [
  [27.98, 84.04],
  [27.9, 84.25],
  [27.82, 84.43],
  [27.76, 84.65],
  [27.68, 84.86],
  [27.58, 85.1],
  [27.5, 85.25],
]

function MapView({ visibleLayers, activeLayer }) {
  return (
    <MapContainer
      center={[27.74, 84.8]}
      zoom={9}
      scrollWheelZoom
      style={{ height: '100%', width: '100%' }}
    >
      <TileLayer
        attribution='&copy; OpenStreetMap contributors'
        url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
      />

      {visibleLayers['Flood Extent'] && (
        <Polygon
          positions={floodCoords}
          pathOptions={{
            color: '#1ea4d8',
            fillColor: activeLayer === 'Water Depth' ? '#2563eb' : '#66c7eb',
            fillOpacity: 0.6,
            weight: 2,
          }}
        />
      )}

      {visibleLayers.River && (
        <Polyline positions={riverCoords} pathOptions={{ color: '#0f6f8f', weight: 4, opacity: 0.95 }} />
      )}

      {visibleLayers.Dam && (
        <Circle
          center={[27.96, 84.1]}
          radius={1800}
          pathOptions={{
            color: '#dd4f4f',
            fillColor: '#dd4f4f',
            fillOpacity: 0.7,
          }}
        />
      )}
    </MapContainer>
  )
}

export default MapView
