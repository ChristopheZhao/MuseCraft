const nextJest = require('next/jest')

const createJestConfig = nextJest({
  // Provide the path to your Next.js app to load next.config.js and .env files
  dir: './',
})

const moduleNameMapper = {
  '^@/(.*)$': '<rootDir>/src/$1',
  '^@/components/(.*)$': '<rootDir>/src/components/$1',
  '^@/pages/(.*)$': '<rootDir>/src/pages/$1',
  '^@/lib/(.*)$': '<rootDir>/src/lib/$1',
  '^@/store/(.*)$': '<rootDir>/src/store/$1',
  '^@/types/(.*)$': '<rootDir>/src/types/$1',
  '^@/hooks/(.*)$': '<rootDir>/src/hooks/$1',
}

const transform = {
  '^.+\\.(js|jsx|ts|tsx)$': ['babel-jest', { presets: ['next/babel'] }],
}

const transformIgnorePatterns = [
  '/node_modules/',
  '^.+\\.module\\.(css|sass|scss)$',
]

const moduleFileExtensions = ['ts', 'tsx', 'js', 'jsx', 'json', 'node']

const testPathIgnorePatterns = [
  '<rootDir>/.next/',
  '<rootDir>/node_modules/',
  '<rootDir>/coverage/',
  '<rootDir>/dist/',
]

const roots = ['<rootDir>/src', '<rootDir>/__tests__']

const sharedProjectConfig = {
  moduleNameMapper,
  transform,
  transformIgnorePatterns,
  moduleFileExtensions,
  testPathIgnorePatterns,
  roots,
}

// Add any custom config to be passed to Jest
const customJestConfig = {
  setupFilesAfterEnv: ['<rootDir>/__tests__/setup.ts'],
  moduleNameMapper,
  roots,
  testEnvironment: 'jest-environment-jsdom',
  collectCoverageFrom: [
    'src/**/*.{js,jsx,ts,tsx}',
    '!src/**/*.d.ts',
    '!src/**/*.stories.{js,jsx,ts,tsx}',
    '!src/**/*.test.{js,jsx,ts,tsx}',
    '!src/**/*.spec.{js,jsx,ts,tsx}',
  ],
  coverageThreshold: {
    global: {
      branches: 75,
      functions: 75,
      lines: 75,
      statements: 75,
    },
  },
  testMatch: [
    '**/__tests__/**/*.{js,jsx,ts,tsx}',
    '**/*.(test|spec).{js,jsx,ts,tsx}',
  ],
  testPathIgnorePatterns: [
    ...testPathIgnorePatterns,
  ],
  transform,
  transformIgnorePatterns,
  moduleFileExtensions,
  watchman: false,
  globals: {
    'ts-jest': {
      tsconfig: 'tsconfig.json',
    },
  },
  // Performance optimization
  maxWorkers: '50%',
  // Test timeout for async operations
  testTimeout: 30000,
  // Custom test environments for different test types
  projects: [
    {
      displayName: 'integration',
      ...sharedProjectConfig,
      testMatch: ['<rootDir>/__tests__/integration/**/*.test.{js,jsx,ts,tsx}'],
      testEnvironment: 'jest-environment-jsdom',
      setupFilesAfterEnv: ['<rootDir>/__tests__/setup.ts'],
    },
    {
      displayName: 'e2e',
      ...sharedProjectConfig,
      testMatch: ['<rootDir>/__tests__/e2e/**/*.test.{js,jsx,ts,tsx}'],
      testEnvironment: 'node',
      setupFilesAfterEnv: ['<rootDir>/__tests__/setup-e2e.ts'],
    },
    {
      displayName: 'performance',
      ...sharedProjectConfig,
      testMatch: ['<rootDir>/__tests__/performance/**/*.test.{js,jsx,ts,tsx}'],
      testEnvironment: 'jest-environment-jsdom',
      setupFilesAfterEnv: ['<rootDir>/__tests__/setup-performance.ts'],
    },
    {
      displayName: 'accessibility',
      ...sharedProjectConfig,
      testMatch: ['<rootDir>/__tests__/accessibility/**/*.test.{js,jsx,ts,tsx}'],
      testEnvironment: 'jest-environment-jsdom',
      setupFilesAfterEnv: ['<rootDir>/__tests__/setup-a11y.ts'],
    },
  ],
}

// createJestConfig is exported this way to ensure that next/jest can load the Next.js config which is async
module.exports = createJestConfig(customJestConfig)
