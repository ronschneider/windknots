/**
 * Infinite scroll functionality for Windknots
 * Supports both article cards and digest entries
 */

(function() {
    'use strict';

    // State
    let currentPage = window.paginatorData?.currentPage || 1;
    let totalPages = window.paginatorData?.totalPages || 1;
    let isLoading = false;
    let hasMore = window.paginatorData?.hasNext || false;
    const basePath = window.paginatorData?.basePath || '/articles/';
    const contentType = window.paginatorData?.contentType || 'articles';

    // DOM elements - support both container types
    const container = document.getElementById('digests-container') || document.getElementById('articles-container');
    const loadMoreEl = document.getElementById('load-more');
    const noMoreEl = document.getElementById('no-more');

    if (!container) return;

    /**
     * Escape HTML to prevent XSS
     */
    function escapeHtml(str) {
        if (!str) return '';
        const div = document.createElement('div');
        div.textContent = str;
        return div.innerHTML;
    }

    /**
     * Format date string
     */
    function formatDate(dateStr) {
        if (!dateStr) return '';
        const date = new Date(dateStr);
        return date.toLocaleDateString('en-US', {
            month: 'short',
            day: 'numeric',
            year: 'numeric'
        });
    }

    /**
     * Create a digest entry element from JSON data
     */
    function createDigestEntry(digest) {
        const entry = document.createElement('article');
        entry.className = 'digest-entry mb-14';

        // Build themes HTML
        let themesHtml = '';
        if (digest.themes && digest.themes.length > 0) {
            const themeItems = digest.themes.map((theme, i) => {
                if (i === 0) {
                    // Lead story — hero with overlay
                    const imageHtml = theme.image
                        ? `<img src="${escapeHtml(theme.image)}" alt="${escapeHtml(theme.title)}" class="w-full h-72 md:h-96 object-cover group-hover:scale-105 transition-transform duration-500">`
                        : `<div class="w-full h-72 md:h-96 bg-gradient-to-br from-slate-700 to-slate-900"></div>`;

                    const tagsHtml = (theme.tags || []).slice(0, 2).map(tag =>
                        `<span class="px-2 py-0.5 bg-copper-500/80 text-white rounded text-xs font-semibold uppercase tracking-wider">${escapeHtml(tag)}</span>`
                    ).join('');

                    return `
                        <div class="group relative rounded-lg overflow-hidden mb-6">
                            ${imageHtml}
                            <div class="absolute inset-0 bg-gradient-to-t from-black/70 via-black/20 to-transparent"></div>
                            <div class="absolute bottom-0 left-0 right-0 p-6 md:p-8">
                                <div class="flex items-center gap-2 mb-2">${tagsHtml}</div>
                                <h3 class="font-display text-2xl md:text-3xl font-bold text-white mb-2 leading-snug">${escapeHtml(theme.title)}</h3>
                                <p class="text-slate-200 text-sm md:text-base line-clamp-2">${escapeHtml(theme.description)}</p>
                                <span class="inline-block mt-3 text-xs text-slate-300 uppercase tracking-wider">${theme.articleCount} articles</span>
                            </div>
                        </div>
                    `;
                } else {
                    // Horizontal card
                    const borderClass = i > 1 ? 'border-t border-slate-200' : '';
                    const imageHtml = theme.image
                        ? `<img src="${escapeHtml(theme.image)}" alt="${escapeHtml(theme.title)}" class="w-28 h-20 md:w-36 md:h-24 object-cover rounded flex-shrink-0">`
                        : `<div class="w-28 h-20 md:w-36 md:h-24 bg-slate-200 rounded flex-shrink-0"></div>`;

                    const tagsHtml = (theme.tags || []).slice(0, 2).map(tag =>
                        `<span class="px-1.5 py-0.5 bg-slate-100 text-slate-500 rounded text-xs">${escapeHtml(tag)}</span>`
                    ).join('');

                    return `
                        <div class="group flex gap-4 py-4 ${borderClass}">
                            ${imageHtml}
                            <div class="flex-grow min-w-0">
                                <h4 class="font-display text-lg font-semibold text-slate-800 line-clamp-2 leading-snug mb-1">${escapeHtml(theme.title)}</h4>
                                <p class="text-sm text-slate-500 line-clamp-2">${escapeHtml(theme.description)}</p>
                                <div class="flex items-center gap-2 mt-1">
                                    <span class="text-xs text-slate-400">${theme.articleCount} articles</span>
                                    ${tagsHtml}
                                </div>
                            </div>
                        </div>
                    `;
                }
            }).join('');

            themesHtml = `<div class="mb-8">${themeItems}</div>`;
        }

        // Build weblinks summary HTML
        let weblinksHtml = '';
        if (digest.weblinks) {
            const counts = [];
            if (digest.weblinks.redditCount > 0) counts.push(`${digest.weblinks.redditCount} discussions`);
            if (digest.weblinks.dealsCount > 0) counts.push(`${digest.weblinks.dealsCount} deals`);
            if (digest.weblinks.tripsCount > 0) counts.push(`${digest.weblinks.tripsCount} trips`);

            if (counts.length > 0) {
                weblinksHtml = `
                    <div class="text-sm text-slate-400">
                        From around the web: ${counts.join(', ')}
                    </div>
                `;
            }
        }

        // Format date
        const dateStr = digest.date ? new Date(digest.date).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' }) : `${escapeHtml(digest.month)} ${escapeHtml(digest.day)}, ${escapeHtml(digest.year)}`;

        entry.innerHTML = `
            <div class="flex items-center gap-4 mb-6">
                <time class="text-sm font-mono text-slate-400 uppercase tracking-wider whitespace-nowrap">${dateStr}</time>
                <hr class="flex-grow border-slate-300">
            </div>
            ${themesHtml}
            ${weblinksHtml}
            <div class="mt-6 pt-4 border-t border-slate-200">
                <a href="${escapeHtml(digest.permalink)}" class="text-copper-600 hover:text-copper-800 text-sm font-semibold uppercase tracking-wider">
                    View full digest &rarr;
                </a>
            </div>
        `;

        return entry;
    }

    /**
     * Create an article card element from JSON data
     */
    function createArticleCard(article) {
        const tagsHtml = (article.tags || []).slice(0, 3).map(tag =>
            `<a href="/tags/${encodeURIComponent(tag)}/" class="tag-pill inline-block px-2 py-1 text-xs font-medium rounded-full bg-copper-100 text-copper-700 hover:bg-copper-200 transition-colors">
                ${escapeHtml(tag)}
            </a>`
        ).join('');

        const imageHtml = article.image
            ? `<img src="${escapeHtml(article.image)}" alt="${escapeHtml(article.title)}" class="w-full h-full object-cover hover:scale-105 transition-transform duration-300" loading="lazy" onerror="this.src='/images/placeholder.jpg'">`
            : `<div class="w-full h-full bg-gradient-to-br from-slate-300 to-slate-500 flex items-center justify-center">
                <svg class="h-16 w-16 text-white opacity-50" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z"/>
                </svg>
            </div>`;

        const formattedDate = formatDate(article.date);

        const card = document.createElement('article');
        card.className = 'article-card bg-white rounded-lg border border-slate-200 overflow-hidden hover:shadow-md transition-shadow duration-200';
        card.dataset.tags = (article.tags || []).join(',');

        card.innerHTML = `
            <a href="${escapeHtml(article.source_url)}" target="_blank" rel="noopener noreferrer" class="block aspect-video overflow-hidden">
                ${imageHtml}
            </a>
            <div class="p-4">
                <div class="flex flex-wrap gap-2 mb-3">
                    ${tagsHtml}
                </div>
                <h2 class="text-lg font-semibold text-slate-900 mb-2 line-clamp-2">
                    <a href="${escapeHtml(article.source_url)}" target="_blank" rel="noopener noreferrer" class="hover:text-copper-700 transition-colors">
                        ${escapeHtml(article.title)}
                    </a>
                </h2>
                <p class="text-slate-500 text-sm mb-4 line-clamp-3">
                    ${escapeHtml(article.summary || '')}
                </p>
                <div class="flex items-center justify-between text-xs text-slate-400">
                    <span class="flex items-center">
                        <svg class="h-4 w-4 mr-1" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 20H5a2 2 0 01-2-2V6a2 2 0 012-2h10a2 2 0 012 2v1m2 13a2 2 0 01-2-2V7m2 13a2 2 0 002-2V9a2 2 0 00-2-2h-2m-4-3H9M7 16h6M7 8h6v4H7V8z"/>
                        </svg>
                        ${escapeHtml(article.source_name || 'Unknown')}
                    </span>
                    <time datetime="${escapeHtml(article.date)}">
                        ${formattedDate}
                    </time>
                </div>
            </div>
        `;

        // Apply current filter
        const currentTag = container.dataset.currentTag || 'all';
        if (currentTag !== 'all' && !(article.tags || []).includes(currentTag)) {
            card.style.display = 'none';
        }

        return card;
    }

    /**
     * Load more content
     */
    async function loadMore() {
        if (isLoading || !hasMore) return;

        isLoading = true;
        if (loadMoreEl) loadMoreEl.classList.remove('hidden');

        try {
            const nextPage = currentPage + 1;
            let url;

            // Determine the correct URL for pagination
            if (basePath === '/' || basePath === '') {
                url = nextPage === 1 ? '/index.json' : `/page/${nextPage}/index.json`;
            } else {
                url = nextPage === 1 ? `${basePath}index.json` : `${basePath}page/${nextPage}/index.json`;
            }

            const response = await fetch(url);

            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }

            const data = await response.json();

            // Handle digests
            if (contentType === 'digests' && data.digests && data.digests.length > 0) {
                const fragment = document.createDocumentFragment();
                data.digests.forEach(digest => {
                    fragment.appendChild(createDigestEntry(digest));
                });
                container.appendChild(fragment);
            }
            // Handle articles
            else if (data.articles && data.articles.length > 0) {
                const fragment = document.createDocumentFragment();
                data.articles.forEach(article => {
                    fragment.appendChild(createArticleCard(article));
                });
                container.appendChild(fragment);
            }

            // Update state
            currentPage = data.page;
            hasMore = data.hasNext;

            if (!hasMore) {
                if (loadMoreEl) loadMoreEl.classList.add('hidden');
                if (noMoreEl) noMoreEl.classList.remove('hidden');
            }

        } catch (error) {
            console.error('Error loading more content:', error);
            hasMore = false;
            if (loadMoreEl) loadMoreEl.classList.add('hidden');
        } finally {
            isLoading = false;
            if (hasMore && loadMoreEl) loadMoreEl.classList.add('hidden');
        }
    }

    /**
     * Check if we should load more (user scrolled near bottom)
     */
    function checkScroll() {
        if (!hasMore || isLoading) return;

        const scrollPosition = window.innerHeight + window.scrollY;
        const threshold = document.documentElement.scrollHeight - 500;

        if (scrollPosition >= threshold) {
            loadMore();
        }
    }

    // Debounced scroll handler
    let scrollTimeout;
    function handleScroll() {
        if (scrollTimeout) return;
        scrollTimeout = setTimeout(() => {
            scrollTimeout = null;
            checkScroll();
        }, 100);
    }

    // Initialize
    window.addEventListener('scroll', handleScroll, { passive: true });

    // Client-side search (only for articles)
    const searchInput = document.getElementById('search-input');
    if (searchInput && contentType === 'articles') {
        let searchTimeout;
        searchInput.addEventListener('input', function(e) {
            clearTimeout(searchTimeout);
            searchTimeout = setTimeout(() => {
                const query = e.target.value.toLowerCase().trim();
                const articles = container.querySelectorAll('.article-card');

                articles.forEach(article => {
                    const title = article.querySelector('h2')?.textContent?.toLowerCase() || '';
                    const summary = article.querySelector('p')?.textContent?.toLowerCase() || '';
                    const tags = article.dataset.tags?.toLowerCase() || '';

                    const matches = !query ||
                        title.includes(query) ||
                        summary.includes(query) ||
                        tags.includes(query);

                    article.style.display = matches ? '' : 'none';
                });
            }, 300);
        });
    }

})();
