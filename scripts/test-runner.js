#!/usr/bin/env node

/**
 * Test Runner and Automation Script
 * 
 * Provides automated test execution, reporting, and CI/CD integration
 */

const { execSync, spawn } = require('child_process')
const fs = require('fs')
const path = require('path')
const os = require('os')

// Configuration
const CONFIG = {
  testTypes: {
    unit: {
      pattern: 'src/**/*.test.{ts,tsx}',
      timeout: 30000,
      maxWorkers: '50%'
    },
    integration: {
      pattern: '__tests__/integration/**/*.test.{ts,tsx}',
      timeout: 60000,
      maxWorkers: '25%'
    },
    e2e: {
      pattern: '__tests__/e2e/**/*.test.{ts,tsx}',
      timeout: 120000,
      maxWorkers: 1
    },
    performance: {
      pattern: '__tests__/performance/**/*.test.{ts,tsx}',
      timeout: 60000,
      maxWorkers: 1
    },
    accessibility: {
      pattern: '__tests__/accessibility/**/*.test.{ts,tsx}',
      timeout: 45000,
      maxWorkers: '25%'
    }
  },
  coverage: {
    threshold: {
      global: {
        branches: 75,
        functions: 75,
        lines: 75,
        statements: 75
      }
    },
    reporters: ['text', 'lcov', 'html', 'json']
  },
  reporting: {
    outputDir: 'test-results',
    formats: ['json', 'junit', 'html']
  }
}

class TestRunner {
  constructor() {
    this.results = {
      summary: {},
      details: [],
      coverage: null,
      performance: {},
      accessibility: {}
    }
    
    this.startTime = Date.now()
    this.outputDir = path.join(process.cwd(), CONFIG.reporting.outputDir)
    
    // Ensure output directory exists
    if (!fs.existsSync(this.outputDir)) {
      fs.mkdirSync(this.outputDir, { recursive: true })
    }
  }

  async run(options = {}) {
    console.log('🚀 Starting comprehensive test suite...\n')
    
    try {
      // Pre-test setup
      await this.setup()
      
      // Run different test types based on options
      const testTypes = options.types || ['unit', 'integration', 'performance', 'accessibility']
      
      for (const testType of testTypes) {
        if (CONFIG.testTypes[testType]) {
          console.log(`\n📋 Running ${testType} tests...`)
          await this.runTestType(testType, options)
        }
      }
      
      // Run E2E tests last (if requested)
      if (testTypes.includes('e2e')) {
        console.log('\n🌐 Running E2E tests...')
        await this.runE2ETests(options)
      }
      
      // Generate reports
      await this.generateReports()
      
      // Display summary
      this.displaySummary()
      
      // Check if tests passed
      const success = this.results.summary.failed === 0
      process.exit(success ? 0 : 1)
      
    } catch (error) {
      console.error('❌ Test execution failed:', error.message)
      process.exit(1)
    }
  }

  async setup() {
    console.log('⚙️  Setting up test environment...')
    
    // Clean previous results
    if (fs.existsSync(this.outputDir)) {
      fs.rmSync(this.outputDir, { recursive: true, force: true })
      fs.mkdirSync(this.outputDir, { recursive: true })
    }
    
    // Check if dependencies are installed
    try {
      execSync('npm list --depth=0', { stdio: 'ignore' })
    } catch (error) {
      console.log('📦 Installing dependencies...')
      execSync('npm install', { stdio: 'inherit' })
    }
    
    // Type check
    console.log('🔍 Running type check...')
    try {
      execSync('npm run type-check', { stdio: 'inherit' })
    } catch (error) {
      throw new Error('Type check failed. Please fix TypeScript errors before running tests.')
    }
    
    console.log('✅ Setup complete\n')
  }

  async runTestType(testType, options) {
    const config = CONFIG.testTypes[testType]
    const startTime = Date.now()
    
    try {
      const jestArgs = [
        '--testPathPattern', config.pattern,
        '--testTimeout', config.timeout.toString(),
        '--maxWorkers', config.maxWorkers,
        '--verbose',
        '--passWithNoTests'
      ]
      
      // Add coverage for unit and integration tests
      if (['unit', 'integration'].includes(testType)) {
        jestArgs.push('--coverage', '--coverageDirectory', path.join(this.outputDir, `coverage-${testType}`))
      }
      
      // Add watch mode for development
      if (options.watch) {
        jestArgs.push('--watch')
      }
      
      // Add specific test file if provided
      if (options.testFile) {
        jestArgs.push(options.testFile)
      }
      
      // Run tests
      const result = await this.runJest(jestArgs)
      
      const duration = Date.now() - startTime
      
      this.results.details.push({
        type: testType,
        success: result.success,
        tests: result.numTotalTests,
        passed: result.numPassedTests,
        failed: result.numFailedTests,
        skipped: result.numPendingTests,
        duration
      })
      
      console.log(`✅ ${testType} tests completed in ${(duration / 1000).toFixed(2)}s`)
      
    } catch (error) {
      console.error(`❌ ${testType} tests failed:`, error.message)
      
      this.results.details.push({
        type: testType,
        success: false,
        error: error.message,
        duration: Date.now() - startTime
      })
    }
  }

  async runE2ETests(options) {
    const startTime = Date.now()
    
    try {
      // Start development server if needed
      let serverProcess = null
      if (!options.skipServer) {
        console.log('🚀 Starting development server...')
        serverProcess = await this.startDevServer()
        await this.waitForServer('http://localhost:3000')
      }
      
      // Run E2E tests
      const result = await this.runJest([
        '--testPathPattern', CONFIG.testTypes.e2e.pattern,
        '--testTimeout', CONFIG.testTypes.e2e.timeout.toString(),
        '--maxWorkers', CONFIG.testTypes.e2e.maxWorkers,
        '--verbose',
        '--setupFilesAfterEnv', '<rootDir>/__tests__/setup-e2e.ts'
      ])
      
      // Stop development server
      if (serverProcess) {
        console.log('🛑 Stopping development server...')
        serverProcess.kill('SIGTERM')
      }
      
      const duration = Date.now() - startTime
      
      this.results.details.push({
        type: 'e2e',
        success: result.success,
        tests: result.numTotalTests,
        passed: result.numPassedTests,
        failed: result.numFailedTests,
        duration
      })
      
      console.log(`✅ E2E tests completed in ${(duration / 1000).toFixed(2)}s`)
      
    } catch (error) {
      console.error('❌ E2E tests failed:', error.message)
      
      this.results.details.push({
        type: 'e2e',
        success: false,
        error: error.message,
        duration: Date.now() - startTime
      })
    }
  }

  async runJest(args) {
    return new Promise((resolve, reject) => {
      const jest = spawn('npx', ['jest', ...args], {
        stdio: 'inherit',
        env: { ...process.env, NODE_ENV: 'test' }
      })
      
      jest.on('close', (code) => {
        if (code === 0) {
          resolve({ success: true, numTotalTests: 0, numPassedTests: 0, numFailedTests: 0, numPendingTests: 0 })
        } else {
          reject(new Error(`Jest exited with code ${code}`))
        }
      })
      
      jest.on('error', (error) => {
        reject(error)
      })
    })
  }

  async startDevServer() {
    return new Promise((resolve, reject) => {
      const server = spawn('npm', ['run', 'dev'], {
        stdio: ['ignore', 'pipe', 'pipe'],
        env: { ...process.env, NODE_ENV: 'development', PORT: '3000' }
      })
      
      server.stdout.on('data', (data) => {
        const output = data.toString()
        if (output.includes('Ready on')) {
          resolve(server)
        }
      })
      
      server.stderr.on('data', (data) => {
        console.error('Server error:', data.toString())
      })
      
      server.on('error', reject)
      
      // Timeout after 60 seconds
      setTimeout(() => {
        reject(new Error('Server failed to start within 60 seconds'))
      }, 60000)
    })
  }

  async waitForServer(url, timeout = 30000) {
    const startTime = Date.now()
    
    while (Date.now() - startTime < timeout) {
      try {
        const response = await fetch(url)
        if (response.ok) {
          console.log('✅ Server is ready')
          return
        }
      } catch (error) {
        // Server not ready yet
      }
      
      await new Promise(resolve => setTimeout(resolve, 1000))
    }
    
    throw new Error(`Server at ${url} did not become ready within ${timeout}ms`)
  }

  async generateReports() {
    console.log('\n📊 Generating test reports...')
    
    // Calculate summary
    this.results.summary = this.results.details.reduce((summary, detail) => {
      summary.total += detail.tests || 0
      summary.passed += detail.passed || 0
      summary.failed += detail.failed || 0
      summary.skipped += detail.skipped || 0
      return summary
    }, { total: 0, passed: 0, failed: 0, skipped: 0 })
    
    // Generate JSON report
    const jsonReport = {
      ...this.results,
      metadata: {
        timestamp: new Date().toISOString(),
        duration: Date.now() - this.startTime,
        environment: {
          node: process.version,
          platform: os.platform(),
          arch: os.arch(),
          memory: process.memoryUsage()
        }
      }
    }
    
    fs.writeFileSync(
      path.join(this.outputDir, 'test-results.json'),
      JSON.stringify(jsonReport, null, 2)
    )
    
    // Generate HTML report
    await this.generateHTMLReport(jsonReport)
    
    // Generate JUnit XML (for CI/CD)
    await this.generateJUnitReport()
    
    console.log(`📁 Reports saved to: ${this.outputDir}`)
  }

  async generateHTMLReport(data) {
    const htmlTemplate = `
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Test Results - ${new Date().toLocaleDateString()}</title>
    <style>
        body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; margin: 0; padding: 20px; background: #f5f5f5; }
        .container { max-width: 1200px; margin: 0 auto; background: white; padding: 30px; border-radius: 8px; box-shadow: 0 2px 8px rgba(0,0,0,0.1); }
        .header { text-align: center; margin-bottom: 30px; }
        .summary { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 20px; margin-bottom: 30px; }
        .metric { background: #f8f9fa; padding: 20px; border-radius: 6px; text-align: center; }
        .metric-value { font-size: 2em; font-weight: bold; margin-bottom: 5px; }
        .metric-label { color: #666; font-size: 0.9em; }
        .passed { color: #28a745; }
        .failed { color: #dc3545; }
        .skipped { color: #ffc107; }
        .details { margin-top: 30px; }
        .test-type { margin-bottom: 20px; padding: 15px; border: 1px solid #ddd; border-radius: 6px; }
        .test-type h3 { margin: 0 0 10px 0; }
        .status-success { background: #d4edda; border-color: #c3e6cb; }
        .status-failed { background: #f8d7da; border-color: #f5c6cb; }
        .timestamp { color: #666; font-size: 0.9em; }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>Test Results Report</h1>
            <p class="timestamp">Generated on ${new Date().toLocaleString()}</p>
        </div>
        
        <div class="summary">
            <div class="metric">
                <div class="metric-value">${data.summary.total}</div>
                <div class="metric-label">Total Tests</div>
            </div>
            <div class="metric">
                <div class="metric-value passed">${data.summary.passed}</div>
                <div class="metric-label">Passed</div>
            </div>
            <div class="metric">
                <div class="metric-value failed">${data.summary.failed}</div>
                <div class="metric-label">Failed</div>
            </div>
            <div class="metric">
                <div class="metric-value skipped">${data.summary.skipped}</div>
                <div class="metric-label">Skipped</div>
            </div>
        </div>
        
        <div class="details">
            <h2>Test Type Details</h2>
            ${data.details.map(detail => `
                <div class="test-type ${detail.success ? 'status-success' : 'status-failed'}">
                    <h3>${detail.type.toUpperCase()} Tests</h3>
                    <p><strong>Status:</strong> ${detail.success ? '✅ Passed' : '❌ Failed'}</p>
                    <p><strong>Duration:</strong> ${((detail.duration || 0) / 1000).toFixed(2)}s</p>
                    ${detail.tests ? `
                        <p><strong>Tests:</strong> ${detail.tests} total, ${detail.passed} passed, ${detail.failed} failed, ${detail.skipped} skipped</p>
                    ` : ''}
                    ${detail.error ? `<p><strong>Error:</strong> ${detail.error}</p>` : ''}
                </div>
            `).join('')}
        </div>
        
        <div class="metadata">
            <h2>Environment Information</h2>
            <p><strong>Node.js:</strong> ${data.metadata.environment.node}</p>
            <p><strong>Platform:</strong> ${data.metadata.environment.platform} (${data.metadata.environment.arch})</p>
            <p><strong>Total Duration:</strong> ${(data.metadata.duration / 1000).toFixed(2)}s</p>
        </div>
    </div>
</body>
</html>
    `
    
    fs.writeFileSync(
      path.join(this.outputDir, 'test-results.html'),
      htmlTemplate
    )
  }

  async generateJUnitReport() {
    // Basic JUnit XML structure for CI/CD integration
    const junitXML = `<?xml version="1.0" encoding="UTF-8"?>
<testsuites name="Frontend Tests" tests="${this.results.summary.total}" failures="${this.results.summary.failed}" time="${(Date.now() - this.startTime) / 1000}">
${this.results.details.map(detail => `
  <testsuite name="${detail.type}" tests="${detail.tests || 1}" failures="${detail.failed || (detail.success ? 0 : 1)}" time="${(detail.duration || 0) / 1000}">
    ${detail.success ? 
      `<testcase name="${detail.type}-tests" time="${(detail.duration || 0) / 1000}"/>` :
      `<testcase name="${detail.type}-tests" time="${(detail.duration || 0) / 1000}">
        <failure message="${detail.error || 'Test failed'}">${detail.error || 'Test suite failed'}</failure>
      </testcase>`
    }
  </testsuite>
`).join('')}
</testsuites>`
    
    fs.writeFileSync(
      path.join(this.outputDir, 'junit-results.xml'),
      junitXML
    )
  }

  displaySummary() {
    const { summary } = this.results
    const duration = (Date.now() - this.startTime) / 1000
    
    console.log('\n' + '='.repeat(60))
    console.log('📊 TEST SUMMARY')
    console.log('='.repeat(60))
    console.log(`Total Tests: ${summary.total}`)
    console.log(`✅ Passed: ${summary.passed}`)
    console.log(`❌ Failed: ${summary.failed}`)
    console.log(`⏸️  Skipped: ${summary.skipped}`)
    console.log(`⏱️  Duration: ${duration.toFixed(2)}s`)
    
    if (summary.failed > 0) {
      console.log('\n❌ Some tests failed. Check the detailed report for more information.')
    } else {
      console.log('\n🎉 All tests passed!')
    }
    
    console.log(`\n📁 Detailed reports: ${this.outputDir}`)
    console.log('='.repeat(60))
  }
}

// CLI Interface
async function main() {
  const args = process.argv.slice(2)
  const options = {}
  
  // Parse command line arguments
  for (let i = 0; i < args.length; i++) {
    const arg = args[i]
    
    switch (arg) {
      case '--watch':
        options.watch = true
        break
      case '--types':
        options.types = args[++i]?.split(',') || []
        break
      case '--file':
        options.testFile = args[++i]
        break
      case '--skip-server':
        options.skipServer = true
        break
      case '--help':
        showHelp()
        process.exit(0)
        break
    }
  }
  
  const runner = new TestRunner()
  await runner.run(options)
}

function showHelp() {
  console.log(`
🧪 Frontend Test Runner

Usage: node scripts/test-runner.js [options]

Options:
  --types <types>     Comma-separated list of test types to run
                      Available: unit,integration,e2e,performance,accessibility
                      Default: unit,integration,performance,accessibility
  
  --file <file>       Run specific test file
  
  --watch             Run tests in watch mode (development)
  
  --skip-server       Skip starting development server for E2E tests
  
  --help              Show this help message

Examples:
  node scripts/test-runner.js                           # Run all tests except E2E
  node scripts/test-runner.js --types unit,integration  # Run only unit and integration tests
  node scripts/test-runner.js --types e2e              # Run only E2E tests
  node scripts/test-runner.js --watch --types unit     # Run unit tests in watch mode
  node scripts/test-runner.js --file Button.test.tsx   # Run specific test file
`)
}

// Run if called directly
if (require.main === module) {
  main().catch(error => {
    console.error('Test runner failed:', error)
    process.exit(1)
  })
}

module.exports = { TestRunner }