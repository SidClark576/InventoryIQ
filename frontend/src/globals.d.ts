export {};

declare global {
  interface Window {
    toggleSidebar: () => void;
    closeSidebar: () => void;
    handleLogout: () => Promise<void>;
  }
}
