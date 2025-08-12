/**
 * End-to-End User Workflow Tests
 * 
 * Tests complete user journeys from start to finish, including:
 * - Video creation workflow
 * - Multi-step form interactions  
 * - Real-time progress monitoring
 * - Result preview and export
 * - Error recovery scenarios
 */
import puppeteer, { Browser, Page } from 'puppeteer'
import { setupFetchMocks, mockApiResponses, TestUtils } from '../setup'

describe('End-to-End User Workflow Tests', () => {
  let browser: Browser
  let page: Page
  
  // Test configuration
  const BASE_URL = process.env.TEST_BASE_URL || 'http://localhost:3000'
  const TEST_TIMEOUT = 60000 // 60 seconds for complex workflows
  
  beforeAll(async () => {
    browser = await puppeteer.launch({
      headless: process.env.CI !== 'false',
      slowMo: process.env.CI ? 0 : 50, // Slow down for debugging
      args: [
        '--no-sandbox',
        '--disable-setuid-sandbox',
        '--disable-dev-shm-usage',
        '--disable-extensions',
        '--disable-gpu',
        '--window-size=1280,720'
      ]
    })
  })

  afterAll(async () => {
    if (browser) {
      await browser.close()
    }
  })

  beforeEach(async () => {
    page = await browser.newPage()
    
    // Set viewport for consistent testing
    await page.setViewport({ width: 1280, height: 720 })
    
    // Mock API responses
    await page.setRequestInterception(true)
    
    page.on('request', request => {
      const url = request.url()
      
      if (url.includes('/api/v1/tasks') && request.method() === 'POST') {
        request.respond({
          status: 201,
          contentType: 'application/json',
          body: JSON.stringify(mockApiResponses.tasks.create)
        })
      } else if (url.includes('/api/v1/tasks/test-task-123')) {
        request.respond({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify(mockApiResponses.tasks.detail)
        })
      } else if (url.includes('/health')) {
        request.respond({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify(mockApiResponses.health)
        })
      } else {
        request.continue()
      }
    })
    
    // Navigate to application
    await page.goto(BASE_URL, { waitUntil: 'networkidle0' })
  })

  afterEach(async () => {
    if (page) {
      await page.close()
    }
  })

  describe('Complete Video Generation Workflow', () => {
    it('should complete full video creation workflow from input to preview', async () => {
      // Step 1: Verify initial page load
      await page.waitForSelector('[data-testid="video-request-form"]', { timeout: 10000 })
      
      const pageTitle = await page.title()
      expect(pageTitle).toMatch(/short video maker/i)
      
      // Step 2: Fill out video request form
      await page.type('#video-prompt', 'Create an engaging video about artificial intelligence and its impact on society')
      
      await page.select('#video-style', 'professional')
      
      await page.evaluate(() => {
        const durationInput = document.querySelector('#duration') as HTMLInputElement
        if (durationInput) {
          durationInput.value = '120'
          durationInput.dispatchEvent(new Event('change', { bubbles: true }))
        }
      })
      
      await page.select('#aspect-ratio', '16:9')
      
      // Step 3: Configure advanced settings
      await page.click('#enable-voice-narration')
      await page.waitForSelector('#voice-selection', { visible: true })
      await page.select('#voice-selection', 'professional-male')
      
      await page.click('#enable-background-music')
      await page.waitForSelector('#music-genre', { visible: true })
      await page.select('#music-genre', 'corporate')
      
      // Step 4: Submit form and verify transition to processing
      await Promise.all([
        page.waitForNavigation({ waitUntil: 'networkidle0' }),
        page.click('button[type="submit"]')
      ])
      
      // Verify processing page loaded
      await page.waitForSelector('[data-testid="real-time-progress"]', { timeout: 10000 })
      
      const processingTitle = await page.$eval('h1', el => el.textContent)
      expect(processingTitle).toMatch(/generating.*video/i)
      
      // Step 5: Monitor real-time progress
      await page.waitForSelector('[data-testid="agent-orchestrator"]')
      
      // Verify agents are displayed
      const agentElements = await page.$$('[data-testid="agent-card"]')
      expect(agentElements.length).toBeGreaterThan(0)
      
      // Check for progress indicators
      const progressBars = await page.$$('[role="progressbar"]')
      expect(progressBars.length).toBeGreaterThan(0)
      
      // Wait for connection status
      await page.waitForSelector('[data-testid="connection-status"]')
      const connectionStatus = await page.$eval('[data-testid="connection-status"]', el => el.textContent)
      expect(connectionStatus).toMatch(/connected|connecting/i)
      
      // Step 6: Simulate WebSocket progress updates
      await page.evaluate(() => {
        // Simulate WebSocket messages for testing
        const mockMessages = [
          {
            type: 'agent-status-update',
            data: {
              agent_id: 'concept-generator',
              status: 'working',
              progress: 25,
              current_task: 'Analyzing AI impact themes'
            }
          },
          {
            type: 'progress-update',
            data: {
              task_id: 'test-task-123',
              overall_progress: 25,
              current_stage: 'concept-generation',
              estimated_time_remaining: 180
            }
          },
          {
            type: 'agent-status-update',
            data: {
              agent_id: 'concept-generator',
              status: 'completed',
              progress: 100,
              result: {
                concept: 'AI society impact narrative'
              }
            }
          },
          {
            type: 'agent-status-update',
            data: {
              agent_id: 'script-writer',
              status: 'working',
              progress: 40,
              current_task: 'Writing engaging AI script'
            }
          }
        ]
        
        // Simulate receiving messages
        mockMessages.forEach((message, index) => {
          setTimeout(() => {
            window.dispatchEvent(new CustomEvent('mockWebSocketMessage', {
              detail: message
            }))
          }, index * 2000)
        })
      })
      
      // Wait for progress updates to be reflected in UI
      await page.waitForFunction(
        () => {
          const conceptAgent = document.querySelector('[data-agent-id="concept-generator"]')
          return conceptAgent && conceptAgent.textContent?.includes('completed')
        },
        { timeout: 15000 }
      )
      
      // Step 7: Verify agent coordination display
      const completedAgent = await page.$('[data-agent-id="concept-generator"][data-status="completed"]')
      expect(completedAgent).toBeTruthy()
      
      const workingAgent = await page.$('[data-agent-id="script-writer"][data-status="working"]')
      expect(workingAgent).toBeTruthy()
      
      // Step 8: Continue simulation until completion
      await page.evaluate(() => {
        const completionMessages = [
          {
            type: 'agent-status-update',
            data: {
              agent_id: 'script-writer',
              status: 'completed',
              progress: 100
            }
          },
          {
            type: 'agent-status-update',
            data: {
              agent_id: 'image-generator',
              status: 'working',
              progress: 60,
              current_task: 'Generating visual elements'
            }
          },
          {
            type: 'result-ready',
            data: {
              task_id: 'test-task-123',
              result_type: 'video',
              status: 'completed',
              output: {
                video_url: 'https://example.com/completed-video.mp4',
                thumbnail_url: 'https://example.com/thumbnail.jpg',
                duration: 120,
                file_size: '85MB'
              }
            }
          }
        ]
        
        completionMessages.forEach((message, index) => {
          setTimeout(() => {
            window.dispatchEvent(new CustomEvent('mockWebSocketMessage', {
              detail: message
            }))
          }, index * 1500)
        })
      })
      
      // Step 9: Wait for completion and transition to preview
      await page.waitForFunction(
        () => window.location.pathname.includes('/preview') || 
              document.querySelector('[data-testid="video-player"]'),
        { timeout: 20000 }
      )
      
      // Step 10: Verify video preview interface
      await page.waitForSelector('[data-testid="video-player"]')
      
      const videoElement = await page.$('video')
      expect(videoElement).toBeTruthy()
      
      const videoSrc = await page.$eval('video', el => el.getAttribute('src'))
      expect(videoSrc).toMatch(/completed-video\.mp4/)
      
      // Verify video controls
      const playButton = await page.$('[data-testid="play-button"]')
      expect(playButton).toBeTruthy()
      
      const progressSlider = await page.$('[data-testid="progress-slider"]')
      expect(progressSlider).toBeTruthy()
      
      // Step 11: Test video playback controls
      await page.click('[data-testid="play-button"]')
      
      // Wait for play state change
      await page.waitForFunction(
        () => {
          const video = document.querySelector('video') as HTMLVideoElement
          return video && !video.paused
        },
        { timeout: 5000 }
      )
      
      // Test pause
      await page.click('[data-testid="pause-button"]')
      
      await page.waitForFunction(
        () => {
          const video = document.querySelector('video') as HTMLVideoElement
          return video && video.paused
        },
        { timeout: 5000 }
      )
      
      // Step 12: Verify export options
      const exportButton = await page.$('[data-testid="export-button"]')
      expect(exportButton).toBeTruthy()
      
      await page.click('[data-testid="export-button"]')
      
      // Verify export modal or options appear
      await page.waitForSelector('[data-testid="export-modal"]', { timeout: 5000 })
      
      const exportOptions = await page.$$('[data-testid="export-option"]')
      expect(exportOptions.length).toBeGreaterThan(0)
      
    }, TEST_TIMEOUT)

    it('should handle error recovery during video generation', async () => {
      // Mock API error response
      await page.setRequestInterception(true)
      
      let requestCount = 0
      page.on('request', request => {
        const url = request.url()
        
        if (url.includes('/api/v1/tasks') && request.method() === 'POST') {
          requestCount++
          
          if (requestCount === 1) {
            // First request fails
            request.respond({
              status: 500,
              contentType: 'application/json',
              body: JSON.stringify({
                error: 'Server temporarily unavailable',
                message: 'Please try again later'
              })
            })
          } else {
            // Second request succeeds
            request.respond({
              status: 201,
              contentType: 'application/json',
              body: JSON.stringify(mockApiResponses.tasks.create)
            })
          }
        } else {
          request.continue()
        }
      })
      
      // Fill form and submit
      await page.type('#video-prompt', 'Test error recovery')
      await page.select('#video-style', 'creative')
      await page.click('button[type="submit"]')
      
      // Should show error notification
      await page.waitForSelector('[data-testid="notification-error"]', { timeout: 10000 })
      
      const errorMessage = await page.$eval('[data-testid="notification-error"]', el => el.textContent)
      expect(errorMessage).toMatch(/server.*unavailable/i)
      
      // Should show retry option
      await page.waitForSelector('[data-testid="retry-button"]')
      
      // Click retry
      await page.click('[data-testid="retry-button"]')
      
      // Should succeed on retry
      await page.waitForSelector('[data-testid="real-time-progress"]', { timeout: 10000 })
      
      // Verify we're in processing state
      const processingIndicator = await page.$('[data-testid="processing-indicator"]')
      expect(processingIndicator).toBeTruthy()
    })
  })

  describe('Multi-Device and Responsive Workflow', () => {
    it('should work correctly on mobile devices', async () => {
      // Set mobile viewport
      await page.setViewport({ width: 375, height: 667 })
      
      await page.goto(BASE_URL, { waitUntil: 'networkidle0' })
      
      // Verify mobile layout
      const mobileHeader = await page.$('[data-testid="mobile-header"]')
      expect(mobileHeader).toBeTruthy()
      
      // Verify form is responsive
      await page.waitForSelector('[data-testid="video-request-form"]')
      
      const formElement = await page.$('[data-testid="video-request-form"]')
      const formBounds = await formElement?.boundingBox()
      
      expect(formBounds?.width).toBeLessThanOrEqual(375)
      
      // Test touch interactions
      await page.tap('#video-prompt')
      await page.type('#video-prompt', 'Mobile test video')
      
      // Test mobile-specific UI elements
      const mobileMenu = await page.$('[data-testid="mobile-menu-toggle"]')
      if (mobileMenu) {
        await page.tap('[data-testid="mobile-menu-toggle"]')
        
        await page.waitForSelector('[data-testid="mobile-menu"]', { visible: true })
        
        const menuVisible = await page.$eval('[data-testid="mobile-menu"]', el => 
          window.getComputedStyle(el).display !== 'none'
        )
        expect(menuVisible).toBe(true)
      }
    })

    it('should handle tablet layout and interactions', async () => {
      // Set tablet viewport
      await page.setViewport({ width: 768, height: 1024 })
      
      await page.goto(BASE_URL, { waitUntil: 'networkidle0' })
      
      // Verify tablet-specific layout elements
      const tabletLayout = await page.$('[data-testid="tablet-layout"]')
      expect(tabletLayout).toBeTruthy()
      
      // Test sidebar behavior on tablet
      const sidebar = await page.$('[data-testid="sidebar"]')
      if (sidebar) {
        const sidebarVisible = await page.$eval('[data-testid="sidebar"]', el => 
          window.getComputedStyle(el).display !== 'none'
        )
        
        // On tablet, sidebar might be collapsed by default
        expect(typeof sidebarVisible).toBe('boolean')
      }
      
      // Test form layout on tablet
      const formContainer = await page.$('[data-testid="form-container"]')
      const containerBounds = await formContainer?.boundingBox()
      
      expect(containerBounds?.width).toBeLessThanOrEqual(768)
      expect(containerBounds?.width).toBeGreaterThan(375) // Larger than mobile
    })
  })

  describe('Accessibility User Workflows', () => {
    it('should support keyboard-only navigation through entire workflow', async () => {
      await page.goto(BASE_URL, { waitUntil: 'networkidle0' })
      
      // Start keyboard navigation
      await page.keyboard.press('Tab')
      
      // Should focus on first interactive element
      let focusedElement = await page.evaluate(() => document.activeElement?.tagName)
      expect(['INPUT', 'BUTTON', 'SELECT', 'TEXTAREA']).toContain(focusedElement)
      
      // Navigate through form using only keyboard
      await page.keyboard.type('Create an accessible video about web development')
      
      await page.keyboard.press('Tab')
      await page.keyboard.press('ArrowDown') // Select style
      await page.keyboard.press('ArrowDown')
      await page.keyboard.press('Enter')
      
      await page.keyboard.press('Tab')
      await page.keyboard.type('60') // Duration
      
      await page.keyboard.press('Tab')
      await page.keyboard.press('Space') // Enable voice narration
      
      // Submit form using keyboard
      await page.keyboard.press('Tab')
      await page.keyboard.press('Enter')
      
      // Verify transition to processing page
      await page.waitForSelector('[data-testid="real-time-progress"]', { timeout: 10000 })
      
      // Verify processing page is keyboard accessible
      await page.keyboard.press('Tab')
      
      const processingFocusedElement = await page.evaluate(() => document.activeElement?.tagName)
      expect(['BUTTON', 'A', 'INPUT']).toContain(processingFocusedElement)
    })

    it('should provide appropriate screen reader announcements', async () => {
      await page.goto(BASE_URL, { waitUntil: 'networkidle0' })
      
      // Verify ARIA labels and roles
      const formAriaLabel = await page.$eval('[data-testid="video-request-form"]', el => 
        el.getAttribute('aria-label')
      )
      expect(formAriaLabel).toBeTruthy()
      
      // Check for proper heading structure
      const headings = await page.$$eval('h1, h2, h3, h4, h5, h6', els => 
        els.map(el => ({ tag: el.tagName, text: el.textContent }))
      )
      
      expect(headings.length).toBeGreaterThan(0)
      expect(headings.some(h => h.tag === 'H1')).toBe(true)
      
      // Verify form field labels
      const promptLabel = await page.$eval('label[for="video-prompt"]', el => el.textContent)
      expect(promptLabel).toMatch(/prompt/i)
      
      // Check for live regions
      const liveRegions = await page.$$('[aria-live]')
      expect(liveRegions.length).toBeGreaterThan(0)
      
      // Test error announcements
      await page.click('button[type="submit"]') // Submit empty form
      
      await page.waitForSelector('[aria-live="polite"]', { timeout: 5000 })
      
      const errorAnnouncement = await page.$eval('[aria-live="polite"]', el => el.textContent)
      expect(errorAnnouncement).toMatch(/required|error/i)
    })
  })

  describe('Performance and Load Testing', () => {
    it('should maintain performance during heavy UI updates', async () => {
      await page.goto(BASE_URL, { waitUntil: 'networkidle0' })
      
      // Start performance monitoring
      await page.tracing.start({ path: 'performance-trace.json', screenshots: true })
      
      // Fill form quickly
      await page.type('#video-prompt', 'Performance test video')
      await page.select('#video-style', 'professional')
      await page.click('button[type="submit"]')
      
      await page.waitForSelector('[data-testid="real-time-progress"]', { timeout: 10000 })
      
      // Simulate rapid progress updates
      await page.evaluate(() => {
        const rapidUpdates = Array.from({ length: 100 }, (_, i) => ({
          type: 'progress-update',
          data: {
            task_id: 'test-task-123',
            overall_progress: i,
            agent_updates: [
              { agent_id: 'concept-generator', progress: Math.min(100, i * 2) },
              { agent_id: 'script-writer', progress: Math.max(0, i - 20) }
            ]
          }
        }))
        
        rapidUpdates.forEach((update, index) => {
          setTimeout(() => {
            window.dispatchEvent(new CustomEvent('mockWebSocketMessage', {
              detail: update
            }))
          }, index * 50) // 50ms intervals
        })
      })
      
      // Wait for all updates to complete
      await page.waitForTimeout(6000)
      
      // Stop tracing
      await page.tracing.stop()
      
      // Verify UI remained responsive
      const finalProgress = await page.$eval('[data-testid="overall-progress"]', el => 
        el.getAttribute('aria-valuenow')
      )
      expect(parseInt(finalProgress || '0')).toBeGreaterThan(90)
      
      // Check for any console errors
      const consoleErrors = await page.evaluate(() => {
        return (window as any).__consoleErrors || []
      })
      expect(consoleErrors).toHaveLength(0)
    })
  })
})