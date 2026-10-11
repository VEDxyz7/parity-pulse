import { useRef, useState, type ReactNode } from 'react'
import { Button } from './Button'

/** Feedback describes a completed read, never a provider update or a changed observation. */
export function ReadRefresh({ refetch, busy, disabled=false, children, beforeRead, description='Stored observations may be unchanged; this does not poll providers.' }: {
  refetch: () => Promise<{ isError: boolean }>; busy: boolean; disabled?: boolean; children: ReactNode; beforeRead?: () => void; description?: string;
}) {
  const pending=useRef(false), [message,setMessage]=useState(''), [reading,setReading]=useState(false)
  async function read() {
    if(pending.current || busy || disabled) return
    pending.current=true;setReading(true);setMessage('Reading…')
    try {
      beforeRead?.()
      const result=await refetch()
      setMessage(result.isError ? 'Read failed. Check the connection and retry.' : `Read completed ${new Date().toLocaleTimeString('en-GB',{timeZone:'UTC'})} UTC. ${description}`)
    } catch { setMessage('Read failed. Check the connection and retry.') }
    finally { pending.current=false;setReading(false) }
  }
  return <span className="read-refresh"><Button className="refresh-button" loading={busy||reading} disabled={disabled} onClick={()=>void read()}>{children}</Button>{message&&<span className="refresh-feedback" role="status" aria-live="polite">{message}</span>}</span>
}
