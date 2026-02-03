/**
 * Nearby Rivers Widget
 * Displays real-time stream flow data from USGS Water Services
 */
(function() {
    'use strict';

    const CACHE_DURATION = 15 * 60 * 1000; // 15 minutes
    const SEARCH_RADIUS_MILES = 50;
    const MAX_RIVERS = 8;

    // Flow grade definitions based on historical percentiles
    const FLOW_GRADES = {
        VERY_LOW: { label: 'Very Low', color: 'flow-grade-very-low', maxPercentile: 10 },
        LOW: { label: 'Low', color: 'flow-grade-low', maxPercentile: 25 },
        NORMAL: { label: 'Normal', color: 'flow-grade-normal', maxPercentile: 75 },
        HIGH: { label: 'High', color: 'flow-grade-high', maxPercentile: 90 },
        BLOWN_OUT: { label: 'Blown Out', color: 'flow-grade-blown-out', maxPercentile: 100 }
    };

    // ========== Location Service ==========
    const LocationService = {
        STORAGE_KEY: 'rivers_widget_location',

        async getUserLocation() {
            // Check for stored location first
            const stored = this.getStoredLocation();
            if (stored) {
                return stored;
            }

            // Try GPS
            try {
                const coords = await this.getGPSLocation();
                const location = {
                    lat: coords.latitude,
                    lon: coords.longitude,
                    source: 'gps',
                    name: 'Current Location'
                };
                this.storeLocation(location);
                return location;
            } catch (e) {
                // GPS failed or denied
                return null;
            }
        },

        getGPSLocation() {
            return new Promise((resolve, reject) => {
                if (!navigator.geolocation) {
                    reject(new Error('Geolocation not supported'));
                    return;
                }

                navigator.geolocation.getCurrentPosition(
                    position => resolve(position.coords),
                    error => reject(error),
                    { enableHighAccuracy: false, timeout: 10000, maximumAge: 300000 }
                );
            });
        },

        async geocodeZip(zip) {
            const cacheKey = `zip_${zip}`;
            const cached = sessionStorage.getItem(cacheKey);
            if (cached) {
                return JSON.parse(cached);
            }

            try {
                const response = await fetch(`https://api.zippopotam.us/us/${zip}`);
                if (!response.ok) {
                    throw new Error('Invalid zip code');
                }
                const data = await response.json();
                const place = data.places[0];
                const result = {
                    lat: parseFloat(place.latitude),
                    lon: parseFloat(place.longitude),
                    name: `${place['place name']}, ${place['state abbreviation']}`,
                    source: 'zip',
                    zip: zip
                };
                sessionStorage.setItem(cacheKey, JSON.stringify(result));
                return result;
            } catch (e) {
                throw new Error('Could not find location for zip code');
            }
        },

        storeLocation(location) {
            localStorage.setItem(this.STORAGE_KEY, JSON.stringify(location));
        },

        getStoredLocation() {
            const stored = localStorage.getItem(this.STORAGE_KEY);
            return stored ? JSON.parse(stored) : null;
        },

        clearLocation() {
            localStorage.removeItem(this.STORAGE_KEY);
        }
    };

    // ========== USGS Service ==========
    const USGSService = {
        CACHE_KEY_PREFIX: 'usgs_',

        getBoundingBox(lat, lon, radiusMiles) {
            // Approximate degrees per mile at given latitude
            const latPerMile = 1 / 69;
            const lonPerMile = 1 / (69 * Math.cos(lat * Math.PI / 180));

            return {
                west: lon - (radiusMiles * lonPerMile),
                south: lat - (radiusMiles * latPerMile),
                east: lon + (radiusMiles * lonPerMile),
                north: lat + (radiusMiles * latPerMile)
            };
        },

        async fetchSitesAndFlow(lat, lon) {
            const cacheKey = `${this.CACHE_KEY_PREFIX}${lat.toFixed(2)}_${lon.toFixed(2)}`;
            const cached = this.getCache(cacheKey);
            if (cached) {
                return cached;
            }

            const bbox = this.getBoundingBox(lat, lon, SEARCH_RADIUS_MILES);

            // Fetch instantaneous discharge values
            const url = new URL('https://waterservices.usgs.gov/nwis/iv/');
            url.searchParams.set('format', 'json');
            url.searchParams.set('bBox', `${bbox.west.toFixed(4)},${bbox.south.toFixed(4)},${bbox.east.toFixed(4)},${bbox.north.toFixed(4)}`);
            url.searchParams.set('parameterCd', '00060'); // Discharge
            url.searchParams.set('siteStatus', 'active');

            try {
                const response = await fetch(url);
                if (!response.ok) {
                    throw new Error('USGS API error');
                }
                const data = await response.json();
                const sites = this.parseSites(data, lat, lon);

                // Get statistics for flow grading
                if (sites.length > 0) {
                    await this.fetchStatistics(sites);
                }

                this.setCache(cacheKey, sites);
                return sites;
            } catch (e) {
                console.error('USGS fetch error:', e);
                throw e;
            }
        },

        parseSites(data, userLat, userLon) {
            if (!data.value || !data.value.timeSeries) {
                return [];
            }

            const sites = data.value.timeSeries.map(ts => {
                const siteLat = parseFloat(ts.sourceInfo.geoLocation.geogLocation.latitude);
                const siteLon = parseFloat(ts.sourceInfo.geoLocation.geogLocation.longitude);
                const distance = this.calculateDistance(userLat, userLon, siteLat, siteLon);

                // Get most recent value
                const values = ts.values[0]?.value || [];
                const latestValue = values[values.length - 1];
                const flow = latestValue ? parseFloat(latestValue.value) : null;

                return {
                    siteCode: ts.sourceInfo.siteCode[0].value,
                    name: this.cleanSiteName(ts.sourceInfo.siteName),
                    lat: siteLat,
                    lon: siteLon,
                    distance: distance,
                    flow: flow,
                    flowUnit: 'cfs',
                    dateTime: latestValue?.dateTime,
                    grade: null, // Will be set after statistics fetch
                    percentile: null
                };
            }).filter(site => site.flow !== null && site.flow >= 0);

            // Sort by distance and take closest
            sites.sort((a, b) => a.distance - b.distance);
            return sites.slice(0, MAX_RIVERS);
        },

        cleanSiteName(name) {
            // Clean up USGS site names (often have "RIVER" or state abbreviations)
            return name
                .replace(/ NEAR .+$/i, '')
                .replace(/ AT .+$/i, '')
                .replace(/ ABV .+$/i, '')
                .replace(/ BLW .+$/i, '')
                .replace(/, [A-Z]{2}$/i, '')
                .split(' ')
                .map(word => word.charAt(0).toUpperCase() + word.slice(1).toLowerCase())
                .join(' ')
                .replace(/\s+/g, ' ')
                .trim()
                .substring(0, 30);
        },

        calculateDistance(lat1, lon1, lat2, lon2) {
            // Haversine formula
            const R = 3959; // Earth's radius in miles
            const dLat = (lat2 - lat1) * Math.PI / 180;
            const dLon = (lon2 - lon1) * Math.PI / 180;
            const a = Math.sin(dLat/2) * Math.sin(dLat/2) +
                      Math.cos(lat1 * Math.PI / 180) * Math.cos(lat2 * Math.PI / 180) *
                      Math.sin(dLon/2) * Math.sin(dLon/2);
            const c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1-a));
            return R * c;
        },

        async fetchStatistics(sites) {
            // Fetch daily statistics for all sites to get percentile data
            const siteIds = sites.map(s => s.siteCode).join(',');
            const url = new URL('https://waterservices.usgs.gov/nwis/stat/');
            url.searchParams.set('format', 'json');
            url.searchParams.set('sites', siteIds);
            url.searchParams.set('statReportType', 'daily');
            url.searchParams.set('statTypeCd', 'all');
            url.searchParams.set('parameterCd', '00060');

            try {
                const response = await fetch(url);
                if (!response.ok) {
                    // Statistics not available, use flow-based estimation
                    this.estimateGrades(sites);
                    return;
                }
                const data = await response.json();
                this.applyStatistics(sites, data);
            } catch (e) {
                // Fall back to estimation
                this.estimateGrades(sites);
            }
        },

        applyStatistics(sites, data) {
            if (!data.value || !data.value.timeSeries) {
                this.estimateGrades(sites);
                return;
            }

            const today = new Date();
            const monthDay = `${String(today.getMonth() + 1).padStart(2, '0')}-${String(today.getDate()).padStart(2, '0')}`;

            // Build a map of site statistics
            const statsMap = {};
            data.value.timeSeries.forEach(ts => {
                const siteCode = ts.sourceInfo.siteCode[0].value;
                const stats = ts.values[0]?.value || [];

                // Find statistics for today's date
                const todayStats = stats.filter(s => {
                    const statDate = s.dateTime?.split('T')[0]?.substring(5); // Get MM-DD
                    return statDate === monthDay;
                });

                if (todayStats.length > 0) {
                    statsMap[siteCode] = {
                        p10: parseFloat(todayStats.find(s => s.statisticCd === 'P10')?.value || 0),
                        p25: parseFloat(todayStats.find(s => s.statisticCd === 'P25')?.value || 0),
                        p50: parseFloat(todayStats.find(s => s.statisticCd === 'P50')?.value || 0),
                        p75: parseFloat(todayStats.find(s => s.statisticCd === 'P75')?.value || 0),
                        p90: parseFloat(todayStats.find(s => s.statisticCd === 'P90')?.value || 0)
                    };
                }
            });

            // Apply grades based on percentiles
            sites.forEach(site => {
                const stats = statsMap[site.siteCode];
                if (stats && stats.p50 > 0) {
                    site.grade = this.gradeFromPercentiles(site.flow, stats);
                } else {
                    // No statistics available, estimate
                    site.grade = this.estimateGrade(site.flow);
                }
            });
        },

        gradeFromPercentiles(flow, stats) {
            if (flow < stats.p10) return FLOW_GRADES.VERY_LOW;
            if (flow < stats.p25) return FLOW_GRADES.LOW;
            if (flow < stats.p75) return FLOW_GRADES.NORMAL;
            if (flow < stats.p90) return FLOW_GRADES.HIGH;
            return FLOW_GRADES.BLOWN_OUT;
        },

        estimateGrades(sites) {
            sites.forEach(site => {
                site.grade = this.estimateGrade(site.flow);
            });
        },

        estimateGrade(flow) {
            // Simple estimation when no statistics available
            // Based on typical stream characteristics
            if (flow < 10) return FLOW_GRADES.VERY_LOW;
            if (flow < 50) return FLOW_GRADES.LOW;
            if (flow < 500) return FLOW_GRADES.NORMAL;
            if (flow < 2000) return FLOW_GRADES.HIGH;
            return FLOW_GRADES.BLOWN_OUT;
        },

        getCache(key) {
            const cached = sessionStorage.getItem(key);
            if (!cached) return null;

            const { data, timestamp } = JSON.parse(cached);
            if (Date.now() - timestamp > CACHE_DURATION) {
                sessionStorage.removeItem(key);
                return null;
            }
            return data;
        },

        setCache(key, data) {
            sessionStorage.setItem(key, JSON.stringify({
                data: data,
                timestamp: Date.now()
            }));
        }
    };

    // ========== Widget Renderer ==========
    const RiversWidget = {
        container: null,
        locationBtn: null,
        locationName: null,
        riversList: null,

        init() {
            this.container = document.getElementById('rivers-widget');
            if (!this.container) return;

            this.locationBtn = document.getElementById('edit-location');
            this.locationName = document.getElementById('location-name');
            this.riversList = document.getElementById('rivers-list');

            this.locationBtn?.addEventListener('click', () => this.showLocationModal());

            this.load();
        },

        async load() {
            this.showLoading();

            const location = await LocationService.getUserLocation();

            if (!location) {
                this.showLocationPrompt();
                return;
            }

            this.updateLocationDisplay(location);

            try {
                const rivers = await USGSService.fetchSitesAndFlow(location.lat, location.lon);
                if (rivers.length === 0) {
                    this.showNoRivers();
                } else {
                    this.renderRivers(rivers);
                }
            } catch (e) {
                this.showError();
            }
        },

        showLoading() {
            if (this.locationName) {
                this.locationName.textContent = 'Loading...';
            }
            if (this.riversList) {
                this.riversList.innerHTML = `
                    <div class="flex items-center justify-center py-8 text-slate-400">
                        <svg class="animate-spin h-5 w-5 mr-2" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                            <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
                            <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                        </svg>
                        <span class="text-sm">Finding rivers...</span>
                    </div>
                `;
            }
        },

        showLocationPrompt() {
            if (this.locationName) {
                this.locationName.textContent = 'Set location';
            }
            if (this.riversList) {
                this.riversList.innerHTML = `
                    <div class="text-center py-6">
                        <p class="text-sm text-slate-500 mb-4">Enter your location to see nearby river conditions</p>
                        <button id="prompt-location-btn" class="px-4 py-2 bg-river-500 text-white text-sm font-medium rounded hover:bg-river-600 transition-colors">
                            Set Location
                        </button>
                    </div>
                `;
                document.getElementById('prompt-location-btn')?.addEventListener('click', () => this.showLocationModal());
            }
        },

        showNoRivers() {
            if (this.riversList) {
                this.riversList.innerHTML = `
                    <div class="text-center py-6">
                        <p class="text-sm text-slate-500">No monitored rivers found within ${SEARCH_RADIUS_MILES} miles</p>
                    </div>
                `;
            }
        },

        showError() {
            if (this.riversList) {
                this.riversList.innerHTML = `
                    <div class="text-center py-6">
                        <p class="text-sm text-slate-500 mb-3">Unable to load river data</p>
                        <button id="retry-btn" class="text-sm text-copper-600 hover:text-copper-700 font-medium">
                            Try again
                        </button>
                    </div>
                `;
                document.getElementById('retry-btn')?.addEventListener('click', () => this.load());
            }
        },

        updateLocationDisplay(location) {
            if (this.locationName) {
                this.locationName.textContent = location.name || 'Unknown';
            }
        },

        renderRivers(rivers) {
            if (!this.riversList) return;

            const html = rivers.map(river => `
                <div class="river-card flex items-center py-2 border-b border-slate-100 last:border-0">
                    <div class="min-w-0 flex-grow">
                        <div class="text-sm font-medium text-slate-700 truncate" title="${river.name}">${river.name}</div>
                        <div class="text-xs text-slate-400">${river.distance.toFixed(1)} mi</div>
                    </div>
                    <div class="w-14 text-right flex-shrink-0 ml-2">
                        <span class="text-sm font-mono text-slate-600">${this.formatFlow(river.flow)}</span>
                    </div>
                    <div class="w-20 flex-shrink-0 ml-2">
                        <span class="px-2 py-0.5 ${river.grade.color} text-xs font-medium rounded-full whitespace-nowrap">
                            ${river.grade.label}
                        </span>
                    </div>
                </div>
            `).join('');

            this.riversList.innerHTML = html;
        },

        formatFlow(flow) {
            if (flow >= 10000) {
                return `${(flow / 1000).toFixed(1)}k`;
            }
            if (flow >= 1000) {
                return flow.toFixed(0);
            }
            return flow.toFixed(1);
        },

        showLocationModal() {
            // Remove existing modal if any
            document.getElementById('location-modal')?.remove();

            const modal = document.createElement('div');
            modal.id = 'location-modal';
            modal.className = 'fixed inset-0 z-50 flex items-center justify-center bg-black/50';
            modal.innerHTML = `
                <div class="bg-white rounded-lg shadow-lg p-6 m-4 max-w-sm w-full">
                    <h3 class="font-display text-lg font-semibold text-slate-800 mb-4">Set Your Location</h3>

                    <div class="space-y-4">
                        <div>
                            <label class="block text-sm text-slate-600 mb-1">Enter ZIP code</label>
                            <input type="text" id="zip-input" placeholder="12345" maxlength="5" pattern="[0-9]{5}"
                                class="w-full px-3 py-2 border border-slate-300 rounded text-sm focus:outline-none focus:border-copper-500">
                            <p id="zip-error" class="text-xs text-red-500 mt-1 hidden"></p>
                        </div>

                        <div class="text-center text-sm text-slate-400">or</div>

                        <button id="use-gps-btn" class="w-full px-4 py-2 border border-slate-300 text-slate-600 text-sm font-medium rounded hover:bg-slate-50 transition-colors">
                            Use Current Location
                        </button>
                    </div>

                    <div class="flex gap-3 mt-6">
                        <button id="cancel-location-btn" class="flex-1 px-4 py-2 border border-slate-300 text-slate-600 text-sm font-medium rounded hover:bg-slate-50 transition-colors">
                            Cancel
                        </button>
                        <button id="save-location-btn" class="flex-1 px-4 py-2 bg-copper-600 text-white text-sm font-medium rounded hover:bg-copper-700 transition-colors">
                            Save
                        </button>
                    </div>
                </div>
            `;

            document.body.appendChild(modal);

            // Event listeners
            const closeModal = () => modal.remove();

            modal.addEventListener('click', (e) => {
                if (e.target === modal) closeModal();
            });

            document.getElementById('cancel-location-btn').addEventListener('click', closeModal);

            document.getElementById('use-gps-btn').addEventListener('click', async () => {
                const btn = document.getElementById('use-gps-btn');
                btn.textContent = 'Getting location...';
                btn.disabled = true;

                try {
                    const coords = await LocationService.getGPSLocation();
                    const location = {
                        lat: coords.latitude,
                        lon: coords.longitude,
                        source: 'gps',
                        name: 'Current Location'
                    };
                    LocationService.storeLocation(location);
                    closeModal();
                    this.load();
                } catch (e) {
                    btn.textContent = 'Location access denied';
                    setTimeout(() => {
                        btn.textContent = 'Use Current Location';
                        btn.disabled = false;
                    }, 2000);
                }
            });

            document.getElementById('save-location-btn').addEventListener('click', async () => {
                const zip = document.getElementById('zip-input').value.trim();
                const errorEl = document.getElementById('zip-error');

                if (!zip || !/^\d{5}$/.test(zip)) {
                    errorEl.textContent = 'Please enter a valid 5-digit ZIP code';
                    errorEl.classList.remove('hidden');
                    return;
                }

                const btn = document.getElementById('save-location-btn');
                btn.textContent = 'Looking up...';
                btn.disabled = true;

                try {
                    const location = await LocationService.geocodeZip(zip);
                    LocationService.storeLocation(location);
                    closeModal();
                    this.load();
                } catch (e) {
                    errorEl.textContent = 'Could not find that ZIP code';
                    errorEl.classList.remove('hidden');
                    btn.textContent = 'Save';
                    btn.disabled = false;
                }
            });

            // Focus the input
            document.getElementById('zip-input').focus();
        }
    };

    // Initialize when DOM is ready
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', () => RiversWidget.init());
    } else {
        RiversWidget.init();
    }
})();
