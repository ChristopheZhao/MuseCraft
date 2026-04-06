/**
 * End-to-End User Workflow Tests
 *
 * Keeps browser-level smoke coverage aligned with the current quick-workspace
 * UI and runtime read-model contract.
 */
import puppeteer, { Browser, HTTPRequest, Page } from 'puppeteer'

type RuntimeNode = {
  id: number
  node_key: string
  node_type: string
  order_index: number
  scope_type: string
  status: string
  revision_index: number
  gate_required: boolean
  artifact_refs: Array<Record<string, unknown>>
  diagnostics: Array<Record<string, unknown>>
}

type RuntimeView = {
  session_id: number
  task_db_id: number
  mode: string
  status: string
  current_node_key?: string | null
  summary_output: Record<string, unknown>
  nodes: RuntimeNode[]
  active_gate?: Record<string, unknown> | null
}

type QuickCurrentRunResponse = {
  task: {
    id: number
    task_id: string
    title: string
    description: string
    status: string
    session_id: string
    input_parameters: Record<string, unknown>
    created_at: string
    updated_at: string
  }
  runtime: RuntimeView
}

describe('End-to-End User Workflow Tests', () => {
  let browser: Browser
  let page: Page

  const BASE_URL = process.env.TEST_BASE_URL || 'http://localhost:3000'
  const TEST_TIMEOUT = 60000
  const nowIso = '2026-03-26T07:41:30Z'

  let currentQuickRunResponse: QuickCurrentRunResponse | null
  let runtimeResponse: RuntimeView
  let createdTaskId: string

  const runningRuntime = (currentNodeKey: string = 'concept'): RuntimeView => ({
    session_id: 42,
    task_db_id: 1,
    mode: 'quick',
    status: 'running',
    current_node_key: currentNodeKey,
    summary_output: {},
    nodes: [
      {
        id: 1,
        node_key: 'concept',
        node_type: 'agent',
        order_index: 0,
        scope_type: 'session',
        status: currentNodeKey === 'concept' ? 'running' : 'completed',
        revision_index: 0,
        gate_required: false,
        artifact_refs: [],
        diagnostics: [],
      },
      {
        id: 2,
        node_key: 'script',
        node_type: 'agent',
        order_index: 1,
        scope_type: 'session',
        status: currentNodeKey === 'script' ? 'running' : 'queued',
        revision_index: 0,
        gate_required: true,
        artifact_refs: [],
        diagnostics: [],
      },
    ],
    active_gate: null,
  })

  const scriptGateRuntime = (): RuntimeView => ({
    ...runningRuntime('script'),
    active_gate: {
      id: 7,
      node_id: 2,
      gate_name: 'script_review',
      status: 'awaiting_human',
      facts: {
        script_preview_text: '这是待确认的脚本片段。',
        trigger_reason: 'initial',
      },
      allowed_actions: ['approve', 'revise', 'replan'],
      recommended_action: 'approve',
    },
  })

  const respondJson = async (request: HTTPRequest, status: number, body: unknown) => {
    await request.respond({
      status,
      contentType: 'application/json',
      body: JSON.stringify(body),
    })
  }

  const clickButtonByText = async (label: string) => {
    const clicked = await page.evaluate((text) => {
      const button = Array.from(document.querySelectorAll('button')).find((candidate) =>
        candidate.textContent?.includes(text)
      ) as HTMLButtonElement | undefined
      if (!button) return false
      button.click()
      return true
    }, label)
    expect(clicked).toBe(true)
  }

  beforeAll(async () => {
    browser = await puppeteer.launch({
      headless: process.env.CI !== 'false',
      slowMo: process.env.CI ? 0 : 50,
      args: [
        '--no-sandbox',
        '--disable-setuid-sandbox',
        '--disable-dev-shm-usage',
        '--disable-extensions',
        '--disable-gpu',
        '--window-size=1280,720',
      ],
    })
  })

  afterAll(async () => {
    if (browser) {
      await browser.close()
    }
  })

  beforeEach(async () => {
    createdTaskId = 'test-task-123'
    currentQuickRunResponse = null
    runtimeResponse = runningRuntime('concept')

    page = await browser.newPage()
    await page.setViewport({ width: 1280, height: 720 })

    await page.evaluateOnNewDocument(() => {
      class MockWebSocket {
        static CONNECTING = 0
        static OPEN = 1
        static CLOSING = 2
        static CLOSED = 3

        readyState = MockWebSocket.CONNECTING
        onopen: ((event: Event) => void) | null = null
        onclose: ((event: CloseEvent) => void) | null = null
        onmessage: ((event: MessageEvent) => void) | null = null
        onerror: ((event: Event) => void) | null = null

        constructor(public url: string) {
          setTimeout(() => {
            this.readyState = MockWebSocket.OPEN
            this.onopen?.(new Event('open'))
          }, 0)
        }

        send() {}

        close() {
          this.readyState = MockWebSocket.CLOSED
          this.onclose?.(new CloseEvent('close', { code: 1000, reason: 'test-close' }))
        }
      }

      // @ts-ignore
      window.WebSocket = MockWebSocket
    })

    await page.setRequestInterception(true)
    page.on('request', async (request) => {
      const url = request.url()

      if (url.includes('/api/v1/tasks/quick/current')) {
        await respondJson(request, 200, currentQuickRunResponse)
        return
      }

      if (url.includes('/api/v1/tasks/') && url.includes('/runtime')) {
        await respondJson(request, 200, runtimeResponse)
        return
      }

      if (url.endsWith('/api/v1/tasks/') && request.method() === 'POST') {
        await respondJson(request, 201, {
          id: 1,
          task_id: createdTaskId,
          title: '新建测试任务',
          status: 'pending',
          progress_percentage: 0,
          current_step: 'queued',
          created_at: nowIso,
          updated_at: nowIso,
        })
        return
      }

      if (url.includes(`/api/v1/tasks/${createdTaskId}`) && !url.includes('/runtime') && !url.includes('/result')) {
        await respondJson(request, 200, {
          id: 1,
          task_id: createdTaskId,
          title: '新建测试任务',
          status: 'running',
          progress_percentage: 50,
          current_step: 'concept',
          input_parameters: {},
          output_metadata: {},
          scenes_count: 0,
          resources_count: 0,
          agent_executions_count: 0,
          created_at: nowIso,
          updated_at: nowIso,
        })
        return
      }

      if (url.includes(`/api/v1/tasks/${createdTaskId}/result`)) {
        await respondJson(request, 200, {})
        return
      }

      await request.continue()
    })
  })

  afterEach(async () => {
    if (page) {
      await page.close()
    }
  })

  describe('Quick Workspace Flow', () => {
    it('restores an unfinished quick run into the runtime workspace', async () => {
      currentQuickRunResponse = {
        task: {
          id: 1,
          task_id: createdTaskId,
          title: '恢复中的任务',
          description: '恢复中的任务描述',
          status: 'running',
          session_id: 'workspace-session-1',
          input_parameters: {
            user_prompt: '恢复中的任务\n\n恢复中的任务描述',
            duration: 30,
            aspect_ratio: '16:9',
          },
          created_at: nowIso,
          updated_at: nowIso,
        },
        runtime: runningRuntime('concept'),
      }

      await page.goto(BASE_URL, { waitUntil: 'networkidle0' })
      await page.waitForFunction(() => document.body.innerText.includes('检测到未完成任务'))

      await clickButtonByText('继续查看当前任务')

      await page.waitForFunction(() => document.body.innerText.includes('运行时状态'))
      const bodyText = await page.evaluate(() => document.body.innerText)

      expect(bodyText).toContain('运行时状态')
      expect(bodyText).toContain('当前节点：概念规划')
      expect(bodyText).toContain('概念规划')
    }, TEST_TIMEOUT)

    it('creates a new run and renders the current runtime read-model', async () => {
      currentQuickRunResponse = null
      runtimeResponse = runningRuntime('concept')

      await page.goto(BASE_URL, { waitUntil: 'networkidle0' })
      await page.waitForFunction(() => document.body.innerText.includes('创建新视频'))

      await page.type('input[type="text"]', '当前主线 smoke')
      await page.type('textarea', '验证 quick workspace 会进入 processing，并展示 runtime read-model。')
      await clickButtonByText('开始生成')

      await page.waitForFunction(() => document.body.innerText.includes('运行时状态'))
      const bodyText = await page.evaluate(() => document.body.innerText)

      expect(bodyText).toContain('运行时状态')
      expect(bodyText).toContain('当前节点：概念规划')
      expect(bodyText).toContain('WS 遥测仅作辅助')
    }, TEST_TIMEOUT)

    it('shows the script gate workspace when runtime requires human review', async () => {
      currentQuickRunResponse = {
        task: {
          id: 1,
          task_id: createdTaskId,
          title: '脚本待审核任务',
          description: '脚本待审核任务描述',
          status: 'running',
          session_id: 'workspace-session-2',
          input_parameters: {
            user_prompt: '脚本待审核任务\n\n脚本待审核任务描述',
            duration: 30,
            aspect_ratio: '16:9',
          },
          created_at: nowIso,
          updated_at: nowIso,
        },
        runtime: scriptGateRuntime(),
      }
      runtimeResponse = scriptGateRuntime()

      await page.goto(BASE_URL, { waitUntil: 'networkidle0' })
      await page.waitForFunction(() => document.body.innerText.includes('检测到未完成任务'))
      await clickButtonByText('继续查看当前任务')

      await page.waitForFunction(() => document.body.innerText.includes('脚本工作台'))
      const bodyText = await page.evaluate(() => document.body.innerText)

      expect(bodyText).toContain('脚本工作台')
      expect(bodyText).toContain('批准并继续')
      expect(bodyText).toContain('等待脚本确认')
    }, TEST_TIMEOUT)
  })
})
