const fs = require('fs');
const path = require('path');

const inputPath = path.resolve(__dirname, '../CCEL_書籍目錄.txt');
const outputPath = path.resolve(__dirname, '../public/ccel_catalog.json');

const raw = fs.readFileSync(inputPath, 'utf8');
const lines = raw.split(/\r?\n/);

const catalog = [];
let currentAuthor = null;

for (let line of lines) {
  line = line.trim();
  if (!line) continue;
  // 作者行：[Name (year)]
  if (/^\[.+\]$/.test(line)) {
    if (currentAuthor) catalog.push(currentAuthor);
    currentAuthor = {
      author: line.replace(/^\[|\]$/g, ''),
      works: []
    };
  } else if (currentAuthor && !/^=+/.test(line)) {
    // 作品行（忽略分隔線）
    currentAuthor.works.push(line.replace(/^[-\s]+/, ''));
  }
}
if (currentAuthor) catalog.push(currentAuthor);

fs.writeFileSync(outputPath, JSON.stringify(catalog, null, 2), 'utf8');
console.log(`已成功解析並輸出到 ${outputPath}`); 