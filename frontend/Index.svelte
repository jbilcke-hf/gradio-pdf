  <script lang="ts">
    import { tick, onMount, onDestroy } from "svelte";
    import PdfUploadText from "./PdfUploadText.svelte";
    import type { Gradio } from "@gradio/utils";
    import { Block, BlockLabel, Empty } from "@gradio/atoms";
    import { BaseButton } from "@gradio/button";
    import { File } from "@gradio/icons";
    import { StatusTracker } from "@gradio/statustracker";
    import type { LoadingStatus } from "@gradio/statustracker";
    import type { FileData } from "@gradio/client";
    import { Upload, ModifyUpload } from "@gradio/upload";
    import * as pdfjsLib from 'pdfjs-dist';

    export let interactive: boolean;
    export let elem_id = "";
    export let elem_classes: string[] = [];
    export let visible = true;
    export let value: FileData | null = null;
    export let container = true;
    export let scale: number | null = null;
    export let root: string;
    export let height: number | null = null;
    export let starting_page: number;
    export let label: string;
    export let proxy_url: string;
    export let min_width: number | undefined = undefined;
    export let loading_status: LoadingStatus;
    export let enable_zoom: boolean = false;
    export let min_zoom: number = 0.5;
    export let max_zoom: number = 2.0;
    export let gradio: Gradio<{
      change: never;
      upload: never;
      clear_status: never;
    }>;

    pdfjsLib.GlobalWorkerOptions.workerSrc = "https://cdn.jsdelivr.net/gh/freddyaboulton/gradio-pdf@main/pdf.worker.min.mjs";
    
    let _value;
    let old_value;
    let pdfDoc;
    let numPages = 1;
    let canvasRefNormal;
    let canvasRefFullscreen;
    let currentZoom = 1.0;
    let zoomSliderRefNormal;
    let zoomSliderRefFullscreen;
    let isMouseOverCanvas = false;
    let pdfCanvasRef;
    let isFullscreen = false;
    let lastTouchDistance = null;
    let isPinching = false;
    let isTransitioning = false;

    // Page cache to store high-resolution pre-rendered pages
    // Each page is rendered once at maximum resolution and cached
    // Zooming just rescales the cached canvas (instant!)
    // Key format: "page" (e.g., "1", "2", "3")
    let pageCache = new Map(); // Map<string, HTMLCanvasElement>
    const MAX_CACHED_PAGES = 5; // Keep 5 pages in cache at most

    $: currentPage = Math.min(Math.max(starting_page, 1), numPages);

    // Reactively render page when currentPage, currentZoom, or fullscreen mode changes
    $: {
      // Reference all dependencies to make them reactive
      const _page = currentPage;
      const _zoom = currentZoom;
      const _fullscreen = isFullscreen;
      const _normalCanvas = canvasRefNormal;
      const _fullscreenCanvas = canvasRefFullscreen;

      if (!isTransitioning && pdfDoc && (_page || _zoom !== undefined)) {
        // Ensure the appropriate canvas is bound before rendering
        const targetCanvas = _fullscreen ? _fullscreenCanvas : _normalCanvas;
        if (targetCanvas) {
          render_page(_page);
        }
      }
    }

    // Update zoom slider progress bars whenever zoom changes or slider refs change
    $: if (currentZoom !== undefined) {
      update_zoom_progress();
    }
    $: if (zoomSliderRefNormal) {
      update_zoom_progress();
    }
    $: if (zoomSliderRefFullscreen) {
      update_zoom_progress();
    }

    function update_zoom_progress() {
      const percentage = ((currentZoom - min_zoom) / (max_zoom - min_zoom)) * 100;
      if (zoomSliderRefNormal) {
        zoomSliderRefNormal.style.setProperty('--zoom-progress', `${percentage}%`);
      }
      if (zoomSliderRefFullscreen) {
        zoomSliderRefFullscreen.style.setProperty('--zoom-progress', `${percentage}%`);
      }
    }

    async function handle_clear() {
      value = null;
      await tick();
      gradio.dispatch("change");
    }

    async function handle_upload({detail}: CustomEvent<FileData>): Promise<void> {
      value = detail;
      await tick();
      gradio.dispatch("upload");
    }


    async function get_doc(value: FileData) {
      const loadingTask = pdfjsLib.getDocument({
        url: value.url,
        cMapUrl: "https://huggingface.co/datasets/freddyaboulton/bucket/resolve/main/cmaps/",
        cMapPacked: true,
      });
      pdfDoc = await loadingTask.promise;
      numPages = pdfDoc.numPages;
      currentPage = Math.min(Math.max(starting_page, 1), numPages)
      pageCache.clear(); // Clear cache when loading new document
      render_page(currentPage);
    }

    async function render_page(currentPage) {
      try {
        // Use the appropriate canvas ref based on current view mode
        const canvasRef = isFullscreen ? canvasRefFullscreen : canvasRefNormal;

        if(!pdfDoc || !canvasRef) return;

        const ctx = canvasRef.getContext('2d');
        if (!ctx) return;

        const devicePixelRatio = window.devicePixelRatio || 1;

        // Cache key is just the page number - we render once at high resolution
        const cacheKey = `${currentPage}`;

        // Get page to calculate dimensions
        const page = await pdfDoc.getPage(currentPage);

        // Calculate base viewport (without zoom)
        let baseViewport = page.getViewport({ scale: 1 });
        if (height) {
          baseViewport = page.getViewport({ scale: height / baseViewport.height });
        }

        // Calculate display dimensions at current zoom
        const displayViewport = page.getViewport({ scale: baseViewport.scale * currentZoom });
        const displayWidth = displayViewport.width * devicePixelRatio;
        const displayHeight = displayViewport.height * devicePixelRatio;

        // Check if high-res page is in cache - if so, just rescale it (fast!)
        if (pageCache.has(cacheKey)) {
          const cachedCanvas = pageCache.get(cacheKey);

          // Update canvas size for current zoom
          canvasRef.width = displayWidth;
          canvasRef.height = displayHeight;
          canvasRef.style.width = displayViewport.width + 'px';
          canvasRef.style.height = displayViewport.height + 'px';

          // Scale the high-res cached image to current zoom - this is instant!
          ctx.imageSmoothingEnabled = true;
          ctx.imageSmoothingQuality = 'high';
          ctx.drawImage(cachedCanvas, 0, 0, cachedCanvas.width, cachedCanvas.height,
                                       0, 0, displayWidth, displayHeight);

          // Preload adjacent pages in background
          preload_adjacent_pages(currentPage);
          return;
        }

        // Page not in cache - render once at maximum resolution
        // This ensures we can zoom in without pixelation
        const renderQualityMultiplier = 3;
        const maxResViewport = page.getViewport({
          scale: baseViewport.scale * max_zoom * devicePixelRatio * renderQualityMultiplier
        });

        // Create offscreen canvas at maximum resolution
        const offscreenCanvas = document.createElement('canvas');
        offscreenCanvas.width = maxResViewport.width;
        offscreenCanvas.height = maxResViewport.height;
        const offscreenCtx = offscreenCanvas.getContext('2d');

        const renderContext = {
          canvasContext: offscreenCtx,
          viewport: maxResViewport,
        };

        await page.render(renderContext).promise;

        // Store the high-res canvas in cache (not ImageData, the canvas itself is faster)
        // Manage cache size
        if (pageCache.size >= MAX_CACHED_PAGES) {
          const firstKey = pageCache.keys().next().value;
          pageCache.delete(firstKey);
        }
        pageCache.set(cacheKey, offscreenCanvas);

        // Now display at current zoom level by scaling
        canvasRef.width = displayWidth;
        canvasRef.height = displayHeight;
        canvasRef.style.width = displayViewport.width + 'px';
        canvasRef.style.height = displayViewport.height + 'px';

        ctx.imageSmoothingEnabled = true;
        ctx.imageSmoothingQuality = 'high';
        ctx.drawImage(offscreenCanvas, 0, 0, offscreenCanvas.width, offscreenCanvas.height,
                                       0, 0, displayWidth, displayHeight);

        // Preload adjacent pages in background
        preload_adjacent_pages(currentPage);
      } catch (error) {
        console.error('Error rendering page:', error);
      }
    }

    async function preload_adjacent_pages(currentPage) {
      // Preload next and previous pages for smooth navigation
      const pagesToPreload = [];
      const prevCacheKey = `${currentPage - 1}`;
      const nextCacheKey = `${currentPage + 1}`;

      if (currentPage > 1 && !pageCache.has(prevCacheKey)) {
        pagesToPreload.push(currentPage - 1);
      }
      if (currentPage < numPages && !pageCache.has(nextCacheKey)) {
        pagesToPreload.push(currentPage + 1);
      }

      // Preload pages in background without blocking
      for (const pageNum of pagesToPreload) {
        try {
          const page = await pdfDoc.getPage(pageNum);
          const devicePixelRatio = window.devicePixelRatio || 1;

          let baseViewport = page.getViewport({ scale: 1 });
          if (height) {
            baseViewport = page.getViewport({ scale: height / baseViewport.height });
          }

          // Render at maximum resolution for all zoom levels
          const renderQualityMultiplier = 3;
          const maxResViewport = page.getViewport({
            scale: baseViewport.scale * max_zoom * devicePixelRatio * renderQualityMultiplier
          });

          // Create an offscreen canvas for rendering at max resolution
          const offscreenCanvas = document.createElement('canvas');
          offscreenCanvas.width = maxResViewport.width;
          offscreenCanvas.height = maxResViewport.height;
          const offscreenCtx = offscreenCanvas.getContext('2d');

          const renderContext = {
            canvasContext: offscreenCtx,
            viewport: maxResViewport,
          };

          await page.render(renderContext).promise;

          // Store the high-res canvas in cache
          // Manage cache size
          if (pageCache.size >= MAX_CACHED_PAGES) {
            const firstKey = pageCache.keys().next().value;
            pageCache.delete(firstKey);
          }

          const cacheKey = `${pageNum}`;
          pageCache.set(cacheKey, offscreenCanvas);
        } catch (error) {
          // Silently fail for preloading errors
          console.warn(`Failed to preload page ${pageNum}:`, error);
        }
      }
    }

    function next_page() {
      if (currentPage >= numPages) {
        return;
      }
      currentPage++;
    }

    function prev_page() {
      if (currentPage == 1) {
        return;
      }
      currentPage--;
    }

    function handle_page_change() {
      if(currentPage < 1) return;
      if(currentPage > numPages) return;
    }

    function zoom_in() {
      const newZoom = Math.min(currentZoom + 0.25, max_zoom);
      if (newZoom !== currentZoom) {
        currentZoom = newZoom;
        // render_page will be called automatically by reactive statement
      }
    }

    function zoom_out() {
      const newZoom = Math.max(currentZoom - 0.25, min_zoom);
      if (newZoom !== currentZoom) {
        currentZoom = newZoom;
        // render_page will be called automatically by reactive statement
      }
    }

    function handle_zoom_change(event) {
      if (isTransitioning) return;
      const newZoom = parseFloat(event.target.value);
      if (newZoom !== currentZoom) {
        currentZoom = newZoom;
      }
    }

    function handle_zoom_input(event) {
      if (isTransitioning) return;
      currentZoom = parseFloat(event.target.value);
    }

    function handle_wheel(event) {
      if (!enable_zoom) return;

      // Only handle pinch-to-zoom gestures (trackpad pinch shows as ctrlKey)
      // Allow normal scrolling for regular mouse wheel
      if (!event.ctrlKey) return;

      // Prevent default zoom behavior for pinch gesture
      event.preventDefault();

      // Determine zoom direction (negative deltaY = zoom in, positive = zoom out)
      const delta = -Math.sign(event.deltaY) * 0.1;
      const newZoom = Math.min(Math.max(currentZoom + delta, min_zoom), max_zoom);

      if (newZoom !== currentZoom) {
        currentZoom = newZoom;
        // render_page will be called automatically by reactive statement
      }
    }

    function get_touch_distance(touch1, touch2) {
      const dx = touch1.clientX - touch2.clientX;
      const dy = touch1.clientY - touch2.clientY;
      return Math.sqrt(dx * dx + dy * dy);
    }

    function handle_touchstart(event) {
      if (!enable_zoom) return;

      if (event.touches.length === 2) {
        isPinching = true;
        lastTouchDistance = get_touch_distance(event.touches[0], event.touches[1]);
        event.preventDefault();
      }
    }

    function handle_touchmove(event) {
      if (!enable_zoom || !isPinching) return;

      if (event.touches.length === 2) {
        event.preventDefault();

        const currentDistance = get_touch_distance(event.touches[0], event.touches[1]);

        if (lastTouchDistance && lastTouchDistance > 0) {
          const scaleFactor = currentDistance / lastTouchDistance;
          const delta = (scaleFactor - 1) * 0.5; // Adjust sensitivity
          const newZoom = Math.min(Math.max(currentZoom + delta, min_zoom), max_zoom);

          if (newZoom !== currentZoom) {
            currentZoom = newZoom;
            // render_page will be called automatically by reactive statement
          }
        }

        lastTouchDistance = currentDistance;
      }
    }

    function handle_touchend(event) {
      if (event.touches.length < 2) {
        isPinching = false;
        lastTouchDistance = null;
      }
    }

    function handle_mouse_enter() {
      isMouseOverCanvas = true;
    }

    function handle_mouse_leave() {
      isMouseOverCanvas = false;
    }

    async function toggle_fullscreen() {
      isTransitioning = true;
      isFullscreen = !isFullscreen;
      if (isFullscreen) {
        // Disable body scroll when entering fullscreen
        document.body.style.overflow = 'hidden';
      } else {
        // Re-enable body scroll when exiting fullscreen
        document.body.style.overflow = '';
      }
      // Wait for DOM update and canvas binding, then re-render
      await tick();
      await tick(); // Double tick to ensure canvas is fully bound
      isTransitioning = false;

      const canvasRef = isFullscreen ? canvasRefFullscreen : canvasRefNormal;
      if (canvasRef && pdfDoc) {
        render_page(currentPage);
      }
    }

    async function exit_fullscreen() {
      isTransitioning = true;
      isFullscreen = false;
      // Re-enable body scroll when exiting fullscreen
      document.body.style.overflow = '';
      // Wait for DOM update and canvas binding, then re-render
      await tick();
      await tick(); // Double tick to ensure canvas is fully bound
      isTransitioning = false;

      if (canvasRefNormal && pdfDoc) {
        render_page(currentPage);
      }
    }

    function handle_keydown(event) {
      if (event.key === 'Escape' && isFullscreen) {
        exit_fullscreen();
      }
    }

    function download_pdf() {
      if (!_value || !_value.url) return;

      // Create a temporary anchor element to trigger download
      const link = document.createElement('a');
      link.href = _value.url;
      link.download = _value.orig_name || 'document.pdf';

      // Append to body, click, and remove
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
    }

    function num_digits(x) {
        return (Math.log10((x ^ (x >> 31)) - (x >> 31)) | 0) + 1;
    }

    function normalise_file(value, root, proxy_url) {
      return value
    }
    
    // Compute the url to fetch the file from the backend\
    // whenever a new value is passed in.
    $: _value = normalise_file(value, root, proxy_url);

    // If the value changes, render the PDF of the currentPage
    $: if(JSON.stringify(old_value) != JSON.stringify(_value)) {
      if (_value){
        get_doc(_value);
      }
      old_value = _value;
      gradio.dispatch("change");
    }

    // Set up keyboard event listener for Escape key
    onMount(() => {
      window.addEventListener('keydown', handle_keydown);
    });

    onDestroy(() => {
      window.removeEventListener('keydown', handle_keydown);
    });
  </script>

  <Block {visible} {elem_id} {elem_classes} {container} {scale} {min_width}>
    {#if loading_status}
      <StatusTracker
        autoscroll={gradio.autoscroll}
        i18n={gradio.i18n}
        {...loading_status}
        on:clear_status={() => gradio.dispatch("clear_status", loading_status)}
      />
    {/if}
    <BlockLabel
      show_label={label !== null}
      Icon={File}
      float={value === null}
      label={label || "File"}
    />
    {#if _value}
      <ModifyUpload i18n={gradio.i18n} on:clear={handle_clear} />
      <div class="pdf-container" style={height ? `height: ${height}px; max-height: ${height}px;` : ''}>
        <div
          class="pdf-canvas"
          bind:this={pdfCanvasRef}
          on:wheel={handle_wheel}
          on:touchstart={handle_touchstart}
          on:touchmove={handle_touchmove}
          on:touchend={handle_touchend}
          on:mouseenter={handle_mouse_enter}
          on:mouseleave={handle_mouse_leave}
        >
          <div class="canvas-wrapper">
            <canvas bind:this={canvasRefNormal}></canvas>
          </div>
        </div>
        {#if enable_zoom}
          <div class="zoom-overlay">
            <div class="zoom-level">
              <span>{Math.round(currentZoom * 100)}%</span>
            </div>
            <span class="zoom-label">+</span>
            <input
              type="range"
              class="zoom-slider"
              bind:this={zoomSliderRefNormal}
              value={currentZoom}
              on:input={handle_zoom_input}
              on:change={handle_zoom_change}
              min={min_zoom}
              max={max_zoom}
              step="0.1"
              orient="vertical"
            />
            <span class="zoom-label">−</span>
          </div>
        {/if}
        <div class="pagination-overlay">
          <button class="nav-button" on:click={prev_page} disabled={currentPage === 1}>
            <svg width="18" height="18" viewBox="0 0 20 20" fill="none" xmlns="http://www.w3.org/2000/svg">
              <path d="M12.5 15L7.5 10L12.5 5" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
            </svg>
          </button>
          <div class="page-count">
            <input type="number" class="page-input" style={`width: ${60 + num_digits(numPages) * 16}px`} bind:value={currentPage} on:change={handle_page_change} min={1} max={numPages}  />
            <span class="page-separator">/</span>
            <span class="page-total">{numPages}</span>
          </div>
          <button class="nav-button" on:click={next_page} disabled={currentPage === numPages}>
            <svg width="18" height="18" viewBox="0 0 20 20" fill="none" xmlns="http://www.w3.org/2000/svg">
              <path d="M7.5 15L12.5 10L7.5 5" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
            </svg>
          </button>

          <div class="toolbar-separator"></div>

          <button class="nav-button" on:click={download_pdf} title="Download PDF">
            <svg width="18" height="18" viewBox="0 0 20 20" fill="none" xmlns="http://www.w3.org/2000/svg">
              <path d="M10 3V13M10 13L6 9M10 13L14 9" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
              <path d="M3 16H17" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>
            </svg>
          </button>

          <button class="nav-button" on:click={toggle_fullscreen} title="Fullscreen">
            <svg width="18" height="18" viewBox="0 0 20 20" fill="none" xmlns="http://www.w3.org/2000/svg">
              <path d="M3 7V3H7M13 3H17V7M17 13V17H13M7 17H3V13" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
            </svg>
          </button>
        </div>
      </div>
    {:else if interactive}
      <Upload
        on:load={handle_upload}
        on:error={({ detail }) => {
          loading_status = loading_status || {};
          loading_status.status = "error";
          gradio.dispatch("error", detail);
        }}
        filetype={".pdf"}
        file_count="single"
        {root}
        max_file_size={gradio.max_file_size}
        upload={gradio.client.upload}
        stream_handler={gradio.client.stream}
      >
        <PdfUploadText/>
      </Upload>
    {:else}
      <Empty unpadded_box={true} size="large"><File /></Empty>
    {/if}
  </Block>

  {#if isFullscreen && _value}
    <div class="fullscreen-overlay">
      <div class="fullscreen-container">
        <div
          class="fullscreen-canvas"
          on:wheel={handle_wheel}
          on:touchstart={handle_touchstart}
          on:touchmove={handle_touchmove}
          on:touchend={handle_touchend}
          on:mouseenter={handle_mouse_enter}
          on:mouseleave={handle_mouse_leave}
        >
          <div class="canvas-wrapper">
            <canvas bind:this={canvasRefFullscreen}></canvas>
          </div>
        </div>

        {#if enable_zoom}
          <div class="zoom-overlay">
            <div class="zoom-level">
              <span>{Math.round(currentZoom * 100)}%</span>
            </div>
            <span class="zoom-label">+</span>
            <input
              type="range"
              class="zoom-slider"
              bind:this={zoomSliderRefFullscreen}
              value={currentZoom}
              on:input={handle_zoom_input}
              on:change={handle_zoom_change}
              min={min_zoom}
              max={max_zoom}
              step="0.1"
              orient="vertical"
            />
            <span class="zoom-label">−</span>
          </div>
        {/if}

        <button class="exit-fullscreen-button" on:click={exit_fullscreen} title="Exit Fullscreen (Esc)">
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
            <path d="M18 6L6 18M6 6L18 18" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
          </svg>
        </button>

        <div class="pagination-overlay">
          <button class="nav-button" on:click={prev_page} disabled={currentPage === 1}>
            <svg width="18" height="18" viewBox="0 0 20 20" fill="none" xmlns="http://www.w3.org/2000/svg">
              <path d="M12.5 15L7.5 10L12.5 5" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
            </svg>
          </button>
          <div class="page-count">
            <input type="number" class="page-input" style={`width: ${60 + num_digits(numPages) * 16}px`} bind:value={currentPage} on:change={handle_page_change} min={1} max={numPages}  />
            <span class="page-separator">/</span>
            <span class="page-total">{numPages}</span>
          </div>
          <button class="nav-button" on:click={next_page} disabled={currentPage === numPages}>
            <svg width="18" height="18" viewBox="0 0 20 20" fill="none" xmlns="http://www.w3.org/2000/svg">
              <path d="M7.5 15L12.5 10L7.5 5" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
            </svg>
          </button>

          <div class="toolbar-separator"></div>

          <button class="nav-button" on:click={download_pdf} title="Download PDF">
            <svg width="18" height="18" viewBox="0 0 20 20" fill="none" xmlns="http://www.w3.org/2000/svg">
              <path d="M10 3V13M10 13L6 9M10 13L14 9" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
              <path d="M3 16H17" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>
            </svg>
          </button>
        </div>
      </div>
    </div>
  {/if}

<style>
  .pdf-container {
    position: relative;
    min-height: 400px;
    max-height: 800px;
    flex-shrink: 0;
    border-radius: 4px;
    border: 1px solid rgba(255, 255, 255, 0.6);
    overflow: hidden;
  }

  .pdf-canvas {
    position: relative;
    overflow: auto;
    width: 100%;
    height: 100%;
    overscroll-behavior: contain;
  }

  .canvas-wrapper {
    display: flex;
    justify-content: center;
    align-items: flex-start;
    min-width: 100%;
    min-height: 100%;
    width: fit-content;
    height: fit-content;
    margin: 0 auto;
  }

  .pdf-canvas canvas {
    border-radius: 4px;
    display: block;
  }

  .zoom-overlay {
    position: absolute;
    top: var(--size-4);
    right: var(--size-4);
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: var(--size-2);
    background: rgba(0, 0, 0, 0.75);
    backdrop-filter: blur(10px);
    -webkit-backdrop-filter: blur(10px);
    border: 1px solid rgba(255, 255, 255, 0.2);
    border-radius: var(--radius-xl);
    padding: var(--size-3) var(--size-2);
    box-shadow:
      0 4px 6px rgba(0, 0, 0, 0.3),
      0 1px 3px rgba(0, 0, 0, 0.2),
      inset 0 0 0 1px rgba(255, 255, 255, 0.1);
    z-index: 10;
    pointer-events: auto;
  }

  .pagination-overlay {
    position: absolute;
    bottom: var(--size-4);
    left: 50%;
    transform: translateX(-50%);
    display: flex;
    flex-direction: row;
    align-items: center;
    gap: var(--size-1);
    background: rgba(0, 0, 0, 0.75);
    backdrop-filter: blur(10px);
    -webkit-backdrop-filter: blur(10px);
    border: 1px solid rgba(255, 255, 255, 0.2);
    border-radius: var(--radius-xl);
    padding: var(--size-1) var(--size-2);
    box-shadow:
      0 4px 6px rgba(0, 0, 0, 0.3),
      0 1px 3px rgba(0, 0, 0, 0.2),
      inset 0 0 0 1px rgba(255, 255, 255, 0.1);
    z-index: 10;
    pointer-events: auto;
  }

  .nav-button {
    display: flex;
    align-items: center;
    justify-content: center;
    background: transparent;
    border: none;
    color: rgba(255, 255, 255, 0.6);
    cursor: pointer;
    padding: var(--size-1);
    border-radius: var(--radius-md);
    transition: all 0.2s ease;
  }

  .nav-button svg {
    width: 18px;
    height: 18px;
  }

  .nav-button:hover:not(:disabled) {
    background: rgba(255, 255, 255, 0.1);
    color: rgba(255, 255, 255, 1);
  }

  .nav-button:active:not(:disabled) {
    transform: scale(0.95);
  }

  .nav-button:disabled {
    opacity: 0.3;
    cursor: not-allowed;
  }

  .page-count {
    font-family: var(--font-mono);
    display: flex;
    flex-direction: row;
    justify-content: center;
    align-items: center;
    gap: var(--size-1);
  }

  .page-input {
    outline: none;
    border: 1px solid transparent;
    background: transparent;
    color: var(--body-text-color);
    font-size: var(--text-lg);
    line-height: var(--line-md);
    text-align: center;
    padding: var(--size-2);
    border-radius: var(--radius-md);
    transition: all 0.2s ease;
    font-family: var(--font-mono);
    font-weight: 600;
  }

  .page-input:hover {
    background: rgba(255, 255, 255, 0.05);
    border-color: rgba(255, 255, 255, 0.2);
  }

  .page-input:focus {
    background: rgba(255, 255, 255, 0.1);
    border-color: var(--color-accent);
    box-shadow: 0 0 0 2px rgba(var(--color-accent-rgb), 0.2);
  }

  .page-separator {
    color: rgba(255, 255, 255, 0.5);
    font-size: var(--text-lg);
    padding: 0 var(--size-1);
    font-weight: 600;
  }

  .page-total {
    color: rgba(255, 255, 255, 0.7);
    font-size: var(--text-lg);
    padding: 0 var(--size-1);
    font-weight: 600;
  }

  .zoom-level {
    font-family: var(--font-mono);
    display: flex;
    align-items: center;
    justify-content: center;
    color: var(--body-text-color);
    font-size: var(--text-xs);
    margin-bottom: var(--size-1);
  }

  .zoom-slider {
    -webkit-appearance: slider-vertical;
    appearance: slider-vertical;
    writing-mode: vertical-lr;
    height: 150px;
    width: var(--size-2);
    cursor: pointer;
    outline: none;
    background: transparent;
    transform: rotate(180deg);
  }

  /* webkit track */
  .zoom-slider::-webkit-slider-runnable-track {
    width: var(--size-2);
    background: var(--neutral-200);
    border-radius: var(--radius-xl);
  }

  /* webkit thumb */
  .zoom-slider::-webkit-slider-thumb {
    -webkit-appearance: none;
    appearance: none;
    height: var(--size-4);
    width: var(--size-4);
    background-color: white;
    border-radius: 50%;
    margin-left: -5px;
    box-shadow:
      0 0 0 1px rgba(247, 246, 246, 0.739),
      1px 1px 4px rgba(0, 0, 0, 0.1);
  }

  .zoom-slider::-webkit-slider-runnable-track {
    background: linear-gradient(
      to bottom,
      var(--color-accent) var(--zoom-progress),
      var(--neutral-200) var(--zoom-progress)
    );
  }

  /* firefox */
  .zoom-slider::-moz-range-track {
    width: var(--size-2);
    background: var(--neutral-200);
    border-radius: var(--radius-xl);
  }

  .zoom-slider::-moz-range-thumb {
    appearance: none;
    height: var(--size-4);
    width: var(--size-4);
    background-color: white;
    border-radius: 50%;
    border: none;
    box-shadow:
      0 0 0 1px rgba(247, 246, 246, 0.739),
      1px 1px 4px rgba(0, 0, 0, 0.1);
  }

  .zoom-slider::-moz-range-progress {
    width: var(--size-2);
    background-color: var(--color-accent);
    border-radius: var(--radius-xl);
  }

  .zoom-label {
    font-family: var(--font-mono);
    font-size: var(--text-md);
    font-weight: bold;
    color: var(--body-text-color);
    user-select: none;
    text-align: center;
  }

  .page-input:disabled {
    -webkit-text-fill-color: var(--body-text-color);
    -webkit-opacity: 1;
    opacity: 1;
  }

  .page-input::placeholder {
    color: rgba(255, 255, 255, 0.3);
  }

  .toolbar-separator {
    width: 1px;
    height: 24px;
    background: rgba(255, 255, 255, 0.2);
    margin: 0 var(--size-1);
  }

  .fullscreen-overlay {
    position: fixed;
    top: 0;
    left: 0;
    right: 0;
    bottom: 0;
    width: 100vw;
    height: 100vh;
    background: rgba(0, 0, 0, 0.95);
    z-index: 9999;
    display: flex;
    align-items: center;
    justify-content: center;
  }

  .fullscreen-container {
    position: relative;
    width: 100%;
    height: 100%;
  }

  .fullscreen-canvas {
    position: relative;
    width: 100%;
    height: 100%;
    overflow: auto;
    overscroll-behavior: contain;
  }

  .fullscreen-canvas .canvas-wrapper {
    display: flex;
    justify-content: center;
    align-items: center;
    min-width: 100%;
    min-height: 100%;
    width: fit-content;
    height: fit-content;
  }

  .exit-fullscreen-button {
    position: absolute;
    top: var(--size-4);
    left: var(--size-4);
    display: flex;
    align-items: center;
    justify-content: center;
    background: rgba(0, 0, 0, 0.75);
    backdrop-filter: blur(10px);
    -webkit-backdrop-filter: blur(10px);
    border: 1px solid rgba(255, 255, 255, 0.2);
    border-radius: var(--radius-xl);
    color: rgba(255, 255, 255, 0.6);
    cursor: pointer;
    padding: var(--size-2);
    transition: all 0.2s ease;
    box-shadow:
      0 4px 6px rgba(0, 0, 0, 0.3),
      0 1px 3px rgba(0, 0, 0, 0.2),
      inset 0 0 0 1px rgba(255, 255, 255, 0.1);
    z-index: 11;
  }

  .exit-fullscreen-button:hover {
    background: rgba(255, 0, 0, 0.75);
    color: rgba(255, 255, 255, 1);
    border-color: rgba(255, 0, 0, 0.5);
  }

  .exit-fullscreen-button:active {
    transform: scale(0.95);
  }

</style>