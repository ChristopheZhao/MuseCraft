/**
 * End-to-End Testing Setup Configuration
 * 
 * Setup for Puppeteer-based E2E tests
 */

// Global test configuration
jest.setTimeout(60000) // 60 seconds for E2E tests

// Mock console methods to avoid test noise
const originalError = console.error
const originalWarn = console.warn

beforeAll(() => {
  console.error = (...args: any[]) => {
    // Only log errors that aren't from expected test scenarios
    if (!args.some(arg => typeof arg === 'string' && arg.includes('Test component error'))) {
      originalError(...args)
    }
  }
  
  console.warn = (...args: any[]) => {
    // Filter out common development warnings during testing
    if (!args.some(arg => typeof arg === 'string' && (
      arg.includes('Warning: ReactDOM.render is deprecated') ||
      arg.includes('Warning: componentWillReceiveProps has been renamed')
    ))) {
      originalWarn(...args)
    }
  }
})

afterAll(() => {
  console.error = originalError
  console.warn = originalWarn
})

// Environment validation
if (!process.env.TEST_BASE_URL && !process.env.CI) {
  console.warn('TEST_BASE_URL not set, using default http://localhost:3000')
}

// Global test utilities
export const E2ETestUtils = {
  // Wait for element with retry
  async waitForElementWithRetry(page: any, selector: string, options: any = {}) {
    const maxRetries = options.maxRetries || 3
    const timeout = options.timeout || 10000
    
    for (let i = 0; i < maxRetries; i++) {
      try {
        await page.waitForSelector(selector, { timeout })
        return
      } catch (error) {
        if (i === maxRetries - 1) throw error
        await page.waitForTimeout(1000)
      }
    }
  },
  
  // Take screenshot for debugging
  async takeDebugScreenshot(page: any, name: string) {
    if (process.env.CI !== 'true') {
      await page.screenshot({ 
        path: `__tests__/screenshots/${name}-${Date.now()}.png`,
        fullPage: true 
      })
    }
  },
  
  // Get performance metrics
  async getPerformanceMetrics(page: any) {
    return await page.evaluate(() => {
      const perfData = performance.getEntriesByType('navigation')[0] as PerformanceNavigationTiming
      return {
        domContentLoaded: perfData.domContentLoadedEventEnd - perfData.domContentLoadedEventStart,
        loadComplete: perfData.loadEventEnd - perfData.loadEventStart,
        firstPaint: performance.getEntriesByType('paint').find(entry => entry.name === 'first-paint')?.startTime,
        firstContentfulPaint: performance.getEntriesByType('paint').find(entry => entry.name === 'first-contentful-paint')?.startTime
      }
    })
  },
  
  // Simulate slow network conditions
  async simulateSlowNetwork(page: any) {
    const client = await page.target().createCDPSession()
    await client.send('Network.emulateNetworkConditions', {
      offline: false,
      downloadThroughput: 100 * 1024, // 100 KB/s
      uploadThroughput: 100 * 1024,   // 100 KB/s
      latency: 100 // 100ms
    })
  },
  
  // Reset network conditions
  async resetNetworkConditions(page: any) {
    const client = await page.target().createCDPSession()
    await client.send('Network.emulateNetworkConditions', {
      offline: false,
      downloadThroughput: -1,
      uploadThroughput: -1,
      latency: 0
    })
  }
}
