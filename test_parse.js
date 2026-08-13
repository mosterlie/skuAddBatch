const fs = require('fs');
const content = fs.readFileSync('d:\\myCoding\\skuAddBatch\\test_sku.txt', 'utf8');
const lines = content.split('\n').map(s => s.trim()).filter(s => s !== '');
let parsedData = [];
if (lines.length > 6 && !lines[0].includes('"-')) {
    const dataLines = lines.slice(6);
    dataLines.forEach(line => {
        let cleanLine = line.trim();
        if (cleanLine.startsWith('"') && cleanLine.endsWith('"')) {
            cleanLine = cleanLine.substring(1, cleanLine.length - 1);
        }
        const parts = cleanLine.split('"-"');
        console.log('Parts:', parts);
        if(parts.length >= 10) {
            parsedData.push({
                imageName: parts[0],
                color: parts[1],
                size: parts[2]
            });
        }
    });
}
console.log('parsed:', parsedData);
