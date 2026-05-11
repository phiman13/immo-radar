import { api } from './client'

export function testTelegram(): Promise<{ success: boolean; message: string }> {
  return api.post('/api/telegram/test')
}
