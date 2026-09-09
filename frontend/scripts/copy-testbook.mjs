import { copyFileSync } from 'node:fs';
for (const file of ['UAT.testbook.html', 'UAT.testbook.json', 'UAT.testbook.css']) {
  copyFileSync(new URL(`../${file}`, import.meta.url), new URL(`../dist/${file}`, import.meta.url));
}
