/**
 * Infinite scroll functionality for Windknots
 */

(function() {
    'use strict';

    // State
    let currentPage = window.paginatorData?.currentPage || 1;
    let totalPages = window.paginatorData?.totalPages || 1;
    let isLoading = false;
    let hasMore = window.paginatorData?.hasNext || false;
    const basePath = window.paginatorData?.basePath || '/articles/';

    // DOM elements
    const container = document.getElementById('articles-container');
    const loadMoreEl = document.getElementById('load-more');
    const noMoreEl = document.getElementById('no-more');

    if (!container) return;

    /**
     * Create an article card element from JSON data
     */
    function createArticleCard(article) {
        const tagsHtml = (article.tags || []).slice(0, 3).map(tag =>
            `<a href="/tags/${encodeURIComponent(tag)}/" class="tag-pill inline-block px-2 py-1 text-xs font-medium rounded-full bg-ocean-100 text-ocean-700 hover:bg-ocean-200 transition-colors">
                ${escapeHtml(tag)}
            </a>`
        ).join('');

        const imageHtml = article.image
            ? `<img src="${escapeHtml(article.image)}" alt="${escapeHtml(article.title)}" class="w-full h-full object-cover hover:scale-105 transition-transform duration-300" loading="lazy" onerror="this.src='/images/placeholder.jpg'">`
            : `<div class="w-full h-full bg-gradient-to-br from-ocean-400 to-ocean-600 flex items-center justify-center">
                <svg class="h-16 w-16 text-white opacity-50" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z"/>
                </svg>
            </div>`;

        const formattedDate = formatDate(article.date);

        const card = document.createElement('article');
        card.className = 'article-card bg-white rounded-xl shadow-sm overflow-hidden hover:shadow-md transition-shadow duration-200';
        card.dataset.tags = (article.tags || []).join(',');

        card.innerHTML = `
            <a href="${escapeHtml(article.source_url)}" target="_blank" rel="noopener noreferrer" class="block aspect-video overflow-hidden">
                ${imageHtml}
            </a>
            <div class="p-4">
                <div class="flex flex-wrap gap-2 mb-3">
                    ${tagsHtml}
                </div>
                <h2 class="text-lg font-semibold text-gray-900 mb-2 line-clamp-2">
                    <a href="${escapeHtml(article.source_url)}" target="_blank" rel="noopener noreferrer" class="hover:text-ocean-600 transition-colors">
                        ${escapeHtml(article.title)}
                    </a>
                </h2>
                <p class="text-gray-600 text-sm mb-4 line-clamp-3">
                    ${escapeHtml(article.summary || '')}
                </p>
                <div class="flex items-center justify-between text-xs text-gray-500">
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
     * Load more articles
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

            // Append new articles
            if (data.articles && data.articles.length > 0) {
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
            console.error('Error loading more articles:', error);
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

    // Client-side search
    const searchInput = document.getElementById('search-input');
    if (searchInput) {
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
