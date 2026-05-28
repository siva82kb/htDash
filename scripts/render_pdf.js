#!/usr/bin/env node
/**
 * Server-side PDF rendering with Puppeteer
 * Usage: node render_pdf.js <input_html_file> <output_pdf_file>
 *
 * The script reads HTML from input file, renders it with Puppeteer,
 * and saves the PDF to the output file. Returns exit code 0 on success,
 * non-zero on failure.
 */

let puppeteer;
try {
  puppeteer = require('puppeteer');
} catch (e) {
  // Fallback: try installing Puppeteer if not found
  console.error('Puppeteer not found. Please run: npm install puppeteer');
  process.exit(1);
}
const fs = require('fs');
const path = require('path');

async function renderPdfFromHtml() {
  const inputHtmlFile = process.argv[2];
  const outputPdfFile = process.argv[3];

  if (!inputHtmlFile || !outputPdfFile) {
    console.error('Usage: node render_pdf.js <input_html_file> <output_pdf_file>');
    process.exit(1);
  }

  let browser;
  try {
    // Read the HTML file
    if (!fs.existsSync(inputHtmlFile)) {
      throw new Error(`Input HTML file not found: ${inputHtmlFile}`);
    }

    const htmlContent = fs.readFileSync(inputHtmlFile, 'utf-8');

    // Launch browser
    browser = await puppeteer.launch({
      headless: 'new',
      args: ['--no-sandbox', '--disable-setuid-sandbox']
    });

    const page = await browser.newPage();

    // Set viewport to A4 size for consistent rendering
    await page.setViewport({ width: 794, height: 1123 });

    // Load HTML content
    await page.setContent(htmlContent, { waitUntil: 'networkidle0' });

    // Wait a bit for any JavaScript to finish rendering
    await page.evaluate(() => {
      return new Promise((resolve) => {
        setTimeout(resolve, 500);
      });
    });

    // Generate PDF with page breaks respected
    await page.pdf({
      path: outputPdfFile,
      format: 'A4',
      margin: {
        top: '10mm',
        bottom: '10mm',
        left: '10mm',
        right: '10mm'
      },
      printBackground: true,
      displayHeaderFooter: false,
      preferCSSPageSize: true
    });

    console.log(`PDF successfully generated: ${outputPdfFile}`);
    await browser.close();
    process.exit(0);

  } catch (error) {
    console.error(`Error rendering PDF: ${error.message}`);
    if (browser) {
      await browser.close();
    }
    process.exit(1);
  }
}

renderPdfFromHtml();