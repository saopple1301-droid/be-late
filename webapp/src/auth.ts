import liff from '@line/liff'

const LIFF_ID = import.meta.env.VITE_LIFF_ID as string

let initPromise: Promise<void> | null = null

export function initLiff(): Promise<void> {
  if (!initPromise) {
    initPromise = liff.init({ liffId: LIFF_ID }).catch((err) => {
      initPromise = null
      throw err
    })
  }
  return initPromise
}

export async function ensureLoggedIn(): Promise<void> {
  await initLiff()
  if (!liff.isLoggedIn()) {
    liff.login({ redirectUri: window.location.href })
    // liff.login() navigates away; nothing after this line runs.
    await new Promise(() => {})
  }
}

export function getIdToken(): string | null {
  return liff.getIDToken()
}

export function logout(): void {
  liff.logout()
  window.location.reload()
}

export function getProfilePicture(): string | undefined {
  try {
    return liff.getDecodedIDToken()?.picture
  } catch {
    return undefined
  }
}

export function isInClient(): boolean {
  try {
    return liff.isInClient()
  } catch {
    return false
  }
}
