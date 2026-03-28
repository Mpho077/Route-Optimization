/** @odoo-module **/

import { Component, onMounted, useRef } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

/**
 * Leaflet-based route map widget for the Route Plan form.
 * Renders task markers + driving polyline on an OpenStreetMap base layer.
 */
class RouteMapWidget extends Component {
    static template = "route_optimization.RouteMapWidget";
    static props = {
        record: { type: Object },
    };

    setup() {
        this.mapRef = useRef("mapContainer");
        this.orm = useService("orm");
        onMounted(() => this.renderMap());
    }

    async renderMap() {
        const record = this.props.record;
        const planId = record.data.id;
        if (!planId) return;

        // Fetch task coordinates from server
        const data = await this.orm.call("route.plan", "get_map_data", [planId]);
        if (!data || !data.tasks) return;

        // Lazy-load Leaflet if not available
        if (typeof L === "undefined") {
            await this._loadLeaflet();
        }

        const container = this.mapRef.el;
        if (!container) return;

        const map = L.map(container);
        L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
            attribution: "© OpenStreetMap contributors",
            maxZoom: 18,
        }).addTo(map);

        const bounds = [];
        const colors = ["#e74c3c", "#3498db", "#2ecc71", "#f39c12", "#9b59b6", "#1abc9c"];

        // Add numbered markers
        for (const task of data.tasks) {
            if (!task.lat || !task.lng) continue;

            const icon = L.divIcon({
                className: "route-marker",
                html: `<div class="route-marker-inner" style="background:${colors[task.order % colors.length]}">${task.order}</div>`,
                iconSize: [28, 28],
                iconAnchor: [14, 14],
            });

            const marker = L.marker([task.lat, task.lng], { icon }).addTo(map);
            marker.bindPopup(
                `<strong>#${task.order}</strong> ${task.name}<br/>` +
                `${task.partner}<br/>` +
                `<em>${task.category}</em>`
            );
            bounds.push([task.lat, task.lng]);
        }

        // Draw route polyline (GeoJSON from OSRM or decoded from Google)
        if (data.geometry) {
            try {
                let coords;
                if (typeof data.geometry === "object" && data.geometry.type === "LineString") {
                    coords = data.geometry.coordinates.map((c) => [c[1], c[0]]);
                }
                if (coords && coords.length) {
                    L.polyline(coords, { color: "#4a90d9", weight: 4, opacity: 0.8 }).addTo(map);
                }
            } catch (e) {
                console.warn("Could not render route geometry:", e);
            }
        }

        if (bounds.length) {
            map.fitBounds(bounds, { padding: [40, 40] });
        } else {
            map.setView([59.9139, 10.7522], 10);
        }
    }

    async _loadLeaflet() {
        return new Promise((resolve, reject) => {
            const link = document.createElement("link");
            link.rel = "stylesheet";
            link.href = "https://unpkg.com/leaflet@1.9.4/dist/leaflet.css";
            document.head.appendChild(link);

            const script = document.createElement("script");
            script.src = "https://unpkg.com/leaflet@1.9.4/dist/leaflet.js";
            script.onload = resolve;
            script.onerror = reject;
            document.head.appendChild(script);
        });
    }
}

registry.category("view_widgets").add("route_map", RouteMapWidget);
