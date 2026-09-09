import { createRoot } from 'react-dom/client';
import { App } from './App';
import './styles.css';

export function mount(root: HTMLElement) { createRoot(root).render(<App />); }
const root = document.getElementById('root');
if (root) mount(root);
