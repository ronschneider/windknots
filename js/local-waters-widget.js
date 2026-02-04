/**
 * Local Waters Widget
 * Combines USGS stream flow data and Orvis fishing reports
 */
(function() {
    'use strict';

    const USGS_CACHE_DURATION = 15 * 60 * 1000; // 15 minutes
    const REPORTS_CACHE_DURATION = 60 * 60 * 1000; // 1 hour
    const SEARCH_RADIUS_MILES = 50;
    const MAX_RIVERS = 6;
    const MAX_REPORTS = 4;
    const REPORTS_URL = '/data/fishing-reports.json';

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
            const stored = this.getStoredLocation();
            if (stored) return stored;

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
            if (cached) return JSON.parse(cached);

            const response = await fetch(`https://api.zippopotam.us/us/${zip}`);
            if (!response.ok) throw new Error('Invalid zip code');

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
            const cached = this.getCache(cacheKey, USGS_CACHE_DURATION);
            if (cached) return cached;

            const bbox = this.getBoundingBox(lat, lon, SEARCH_RADIUS_MILES);
            const url = new URL('https://waterservices.usgs.gov/nwis/iv/');
            url.searchParams.set('format', 'json');
            url.searchParams.set('bBox', `${bbox.west.toFixed(4)},${bbox.south.toFixed(4)},${bbox.east.toFixed(4)},${bbox.north.toFixed(4)}`);
            url.searchParams.set('parameterCd', '00060');
            url.searchParams.set('siteStatus', 'active');

            const response = await fetch(url);
            if (!response.ok) throw new Error('USGS API error');

            const data = await response.json();
            const sites = this.parseSites(data, lat, lon);

            if (sites.length > 0) {
                await this.fetchStatistics(sites);
            }

            this.setCache(cacheKey, sites);
            return sites;
        },

        parseSites(data, userLat, userLon) {
            if (!data.value || !data.value.timeSeries) return [];

            const sites = data.value.timeSeries.map(ts => {
                const siteLat = parseFloat(ts.sourceInfo.geoLocation.geogLocation.latitude);
                const siteLon = parseFloat(ts.sourceInfo.geoLocation.geogLocation.longitude);
                const distance = calculateDistance(userLat, userLon, siteLat, siteLon);

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
                    grade: null,
                    percentile: null
                };
            }).filter(site => site.flow !== null && site.flow >= 0);

            sites.sort((a, b) => a.distance - b.distance);
            return sites.slice(0, MAX_RIVERS);
        },

        cleanSiteName(name) {
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

        async fetchStatistics(sites) {
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
                    this.estimateGrades(sites);
                    return;
                }
                const data = await response.json();
                this.applyStatistics(sites, data);
            } catch (e) {
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

            const statsMap = {};
            data.value.timeSeries.forEach(ts => {
                const siteCode = ts.sourceInfo.siteCode[0].value;
                const stats = ts.values[0]?.value || [];
                const todayStats = stats.filter(s => {
                    const statDate = s.dateTime?.split('T')[0]?.substring(5);
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

            sites.forEach(site => {
                const stats = statsMap[site.siteCode];
                if (stats && stats.p50 > 0) {
                    site.grade = this.gradeFromPercentiles(site.flow, stats);
                } else {
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
            if (flow < 10) return FLOW_GRADES.VERY_LOW;
            if (flow < 50) return FLOW_GRADES.LOW;
            if (flow < 500) return FLOW_GRADES.NORMAL;
            if (flow < 2000) return FLOW_GRADES.HIGH;
            return FLOW_GRADES.BLOWN_OUT;
        },

        getCache(key, duration) {
            const cached = sessionStorage.getItem(key);
            if (!cached) return null;
            const { data, timestamp } = JSON.parse(cached);
            if (Date.now() - timestamp > duration) {
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

    // ========== Fishing Reports Service ==========
    const ReportsService = {
        CACHE_KEY: 'fishing_reports_cache',

        async fetchReports(lat, lon) {
            const cached = this.getCache();
            let reports = cached;

            if (!reports) {
                const response = await fetch(REPORTS_URL);
                if (!response.ok) throw new Error('Failed to fetch reports');
                const data = await response.json();
                reports = data.reports || [];
                this.setCache(reports);
            }

            // Sort by distance
            return reports
                .map(report => ({
                    ...report,
                    distance: calculateDistance(lat, lon, report.lat, report.lon)
                }))
                .sort((a, b) => a.distance - b.distance)
                .slice(0, MAX_REPORTS);
        },

        getCache() {
            const cached = sessionStorage.getItem(this.CACHE_KEY);
            if (!cached) return null;
            const { data, timestamp } = JSON.parse(cached);
            if (Date.now() - timestamp > REPORTS_CACHE_DURATION) {
                sessionStorage.removeItem(this.CACHE_KEY);
                return null;
            }
            return data;
        },

        setCache(data) {
            sessionStorage.setItem(this.CACHE_KEY, JSON.stringify({
                data: data,
                timestamp: Date.now()
            }));
        }
    };

    // ========== Shared Utilities ==========
    function calculateDistance(lat1, lon1, lat2, lon2) {
        const R = 3959;
        const dLat = (lat2 - lat1) * Math.PI / 180;
        const dLon = (lon2 - lon1) * Math.PI / 180;
        const a = Math.sin(dLat/2) * Math.sin(dLat/2) +
                  Math.cos(lat1 * Math.PI / 180) * Math.cos(lat2 * Math.PI / 180) *
                  Math.sin(dLon/2) * Math.sin(dLon/2);
        const c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1-a));
        return R * c;
    }

    function formatFlow(flow) {
        if (flow >= 10000) return `${(flow / 1000).toFixed(1)}k`;
        if (flow >= 1000) return flow.toFixed(0);
        return flow.toFixed(1);
    }

    function escapeHtml(str) {
        if (!str) return '';
        const div = document.createElement('div');
        div.textContent = str;
        return div.innerHTML;
    }

    function getRatingClass(rating) {
        if (!rating) return 'bg-slate-100 text-slate-600';
        const lower = rating.toLowerCase();
        if (lower.includes('hot')) return 'bg-red-100 text-red-700';
        if (lower.includes('excellent')) return 'bg-green-100 text-green-700';
        if (lower.includes('good')) return 'bg-blue-100 text-blue-700';
        return 'bg-slate-100 text-slate-600';
    }

    function formatRelativeTime(dateStr) {
        if (!dateStr) return null;
        try {
            const date = new Date(dateStr);
            if (isNaN(date.getTime())) return null;

            const now = new Date();
            const diffMs = now - date;
            const diffDays = Math.floor(diffMs / (1000 * 60 * 60 * 24));

            if (diffDays < 0) return 'upcoming';
            if (diffDays === 0) return 'today';
            if (diffDays === 1) return '1d ago';
            if (diffDays < 7) return `${diffDays}d ago`;
            if (diffDays < 14) return '1w ago';
            if (diffDays < 30) return `${Math.floor(diffDays / 7)}w ago`;
            if (diffDays < 60) return '1mo ago';
            return `${Math.floor(diffDays / 30)}mo ago`;
        } catch {
            return null;
        }
    }

    function getAgeClass(dateStr) {
        if (!dateStr) return 'text-slate-400';
        try {
            const date = new Date(dateStr);
            if (isNaN(date.getTime())) return 'text-slate-400';

            const diffDays = Math.floor((new Date() - date) / (1000 * 60 * 60 * 24));

            if (diffDays <= 2) return 'text-green-600';
            if (diffDays <= 7) return 'text-amber-600';
            return 'text-red-500';
        } catch {
            return 'text-slate-400';
        }
    }

    // ========== Widget Renderer ==========
    const LocalWatersWidget = {
        container: null,
        locationBtn: null,
        locationName: null,
        flowList: null,
        reportsList: null,

        init() {
            this.container = document.getElementById('local-waters-widget');
            if (!this.container) return;

            this.locationBtn = document.getElementById('edit-location');
            this.locationName = document.getElementById('location-name');
            this.flowList = document.getElementById('flow-list');
            this.reportsList = document.getElementById('reports-list');

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

            // Fetch both data sources in parallel
            const [flowResult, reportsResult] = await Promise.allSettled([
                USGSService.fetchSitesAndFlow(location.lat, location.lon),
                ReportsService.fetchReports(location.lat, location.lon)
            ]);

            // Render flow data
            if (flowResult.status === 'fulfilled' && flowResult.value.length > 0) {
                this.renderFlow(flowResult.value);
            } else {
                this.showNoFlow();
            }

            // Render reports
            if (reportsResult.status === 'fulfilled' && reportsResult.value.length > 0) {
                this.renderReports(reportsResult.value);
            } else {
                this.showNoReports();
            }
        },

        showLoading() {
            if (this.locationName) {
                this.locationName.textContent = 'Loading...';
            }
            const loadingHtml = `
                <div class="flex items-center justify-center py-4 text-slate-400">
                    <svg class="animate-spin h-4 w-4 mr-2" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                        <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
                        <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                    </svg>
                    <span class="text-xs">Loading...</span>
                </div>
            `;
            if (this.flowList) this.flowList.innerHTML = loadingHtml;
            if (this.reportsList) this.reportsList.innerHTML = loadingHtml;
        },

        showLocationPrompt() {
            if (this.locationName) {
                this.locationName.textContent = 'Set location';
            }
            const promptHtml = `
                <div class="text-center py-4">
                    <p class="text-xs text-slate-500 mb-3">Set your location to see local conditions</p>
                    <button class="prompt-location-btn px-3 py-1.5 bg-river-500 text-white text-xs font-medium rounded hover:bg-river-600 transition-colors">
                        Set Location
                    </button>
                </div>
            `;
            if (this.flowList) {
                this.flowList.innerHTML = promptHtml;
                this.flowList.querySelector('.prompt-location-btn')?.addEventListener('click', () => this.showLocationModal());
            }
            if (this.reportsList) {
                this.reportsList.innerHTML = '';
            }
        },

        showNoFlow() {
            if (this.flowList) {
                this.flowList.innerHTML = `
                    <div class="text-center py-3 text-xs text-slate-400">
                        No gauges found within ${SEARCH_RADIUS_MILES} mi
                    </div>
                `;
            }
        },

        showNoReports() {
            if (this.reportsList) {
                this.reportsList.innerHTML = `
                    <div class="text-center py-3 text-xs text-slate-400">
                        No reports nearby
                    </div>
                `;
            }
        },

        updateLocationDisplay(location) {
            if (this.locationName) {
                this.locationName.textContent = location.name || 'Unknown';
            }
        },

        renderFlow(rivers) {
            if (!this.flowList) return;

            const html = rivers.map(river => `
                <div class="flex items-center py-1.5 border-b border-slate-100 last:border-0">
                    <div class="min-w-0 flex-grow">
                        <div class="text-xs font-medium text-slate-700 truncate" title="${river.name}">${river.name}</div>
                        <div class="text-[10px] text-slate-400">${river.distance.toFixed(1)} mi</div>
                    </div>
                    <div class="text-right flex-shrink-0 ml-2">
                        <span class="text-xs font-mono text-slate-600">${formatFlow(river.flow)}</span>
                    </div>
                    <div class="flex-shrink-0 ml-2">
                        <span class="px-1.5 py-0.5 ${river.grade.color} text-[10px] font-medium rounded whitespace-nowrap">
                            ${river.grade.label}
                        </span>
                    </div>
                </div>
            `).join('');

            this.flowList.innerHTML = html;
        },

        renderReports(reports) {
            if (!this.reportsList) return;

            const html = reports.map(report => {
                const age = formatRelativeTime(report.updated);
                const ageClass = getAgeClass(report.updated);

                return `
                <a href="${report.url}" target="_blank" rel="noopener"
                   class="block py-2 border-b border-slate-100 last:border-0 hover:bg-slate-50 -mx-1 px-1 rounded transition-colors">
                    <div class="flex justify-between items-start gap-1">
                        <div class="text-xs font-medium text-slate-700 truncate flex-grow" title="${escapeHtml(report.name)}">${escapeHtml(report.name)}</div>
                        ${age ? `<span class="flex-shrink-0 text-[10px] font-semibold ${ageClass}">${age}</span>` : ''}
                        ${report.rating ? `<span class="flex-shrink-0 px-1.5 py-0.5 ${getRatingClass(report.rating)} text-[10px] font-medium rounded">${report.rating}</span>` : ''}
                    </div>
                    <div class="text-[10px] text-slate-400 mt-0.5">
                        ${report.state}${report.distance ? ` · ${Math.round(report.distance)} mi` : ''}
                        ${report.water_temp ? ` · ${report.water_temp}` : ''}
                    </div>
                    ${report.conditions ? `<div class="text-[10px] text-slate-500 mt-1 line-clamp-2">${escapeHtml(report.conditions)}</div>` : ''}
                </a>
            `}).join('');

            this.reportsList.innerHTML = html;
        },

        showLocationModal() {
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

            document.getElementById('zip-input').focus();
        }
    };

    // Initialize when DOM is ready
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', () => LocalWatersWidget.init());
    } else {
        LocalWatersWidget.init();
    }
})();
