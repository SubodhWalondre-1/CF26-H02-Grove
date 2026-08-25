class MedioraWebSocket {
  constructor() {
    this.ws = null
    this.handlers = {} // { [eventType: string]: Set<Function> }
    this.reconnectDelay = 1000
    this.maxReconnectDelay = 30000
    this.reconnectTimer = null
    this.token = null
    this.intentionallyClosed = false
    this.isConnected = false
  }

  connect(token) {
    if (!token) return

    this.token = token
    this.intentionallyClosed = false

    if (this.ws && (this.ws.readyState === WebSocket.OPEN || this.ws.readyState === WebSocket.CONNECTING)) {
      return
    }

    const wsBaseUrl = import.meta.env.VITE_WS_URL || 'ws://localhost:8000/ws/dashboard'
    const fullUrl = `${wsBaseUrl}?token=${encodeURIComponent(token)}`

    try {
      this.ws = new WebSocket(fullUrl)

      this.ws.onopen = () => {
        this.isConnected = true
        this.reconnectDelay = 1000
        this._dispatch('*', { event: 'WS_CONNECTED', timestamp: new Date().toISOString() })
      }

      this.ws.onmessage = (event) => {
        this._onMessage(event)
      }

      this.ws.onerror = (error) => {
        console.warn('Mediora WebSocket error:', error)
      }

      this.ws.onclose = (event) => {
        this.isConnected = false
        this._dispatch('*', { event: 'WS_DISCONNECTED', code: event.code, timestamp: new Date().toISOString() })
        if (!this.intentionallyClosed) {
          this._scheduleReconnect()
        }
      }
    } catch (err) {
      console.warn('Failed to establish WebSocket connection:', err)
      this._scheduleReconnect()
    }
  }

  disconnect() {
    this.intentionallyClosed = true
    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer)
      this.reconnectTimer = null
    }
    if (this.ws) {
      this.ws.close()
      this.ws = null
    }
    this.isConnected = false
  }

  subscribe(eventType, handler) {
    if (!this.handlers[eventType]) {
      this.handlers[eventType] = new Set()
    }
    this.handlers[eventType].add(handler)

    // Return unsubscribe callback for React useEffect convenience
    return () => this.unsubscribe(eventType, handler)
  }

  unsubscribe(eventType, handler) {
    if (this.handlers[eventType]) {
      this.handlers[eventType].delete(handler)
      if (this.handlers[eventType].size === 0) {
        delete this.handlers[eventType]
      }
    }
  }

  _onMessage(event) {
    try {
      const data = JSON.parse(event.data)
      const eventType = data.event

      if (eventType) {
        this._dispatch(eventType, data)
      }
      this._dispatch('*', data)
    } catch (err) {
      console.warn('Error parsing incoming WebSocket JSON message:', err, event.data)
    }
  }

  _dispatch(eventType, data) {
    const callbacks = this.handlers[eventType]
    if (callbacks) {
      callbacks.forEach((cb) => {
        try {
          cb(data)
        } catch (err) {
          console.error(`Error in WebSocket subscriber callback for '${eventType}':`, err)
        }
      })
    }
  }

  _scheduleReconnect() {
    if (this.intentionallyClosed || !this.token) return

    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer)
    }

    this.reconnectTimer = setTimeout(() => {
      this.connect(this.token)
      this.reconnectDelay = Math.min(this.reconnectDelay * 2, this.maxReconnectDelay)
    }, this.reconnectDelay)
  }
}

export const wsManager = new MedioraWebSocket()
