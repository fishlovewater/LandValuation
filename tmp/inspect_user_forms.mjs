import { FileBlob, SpreadsheetFile } from "@oai/artifact-tool";

const paths = process.argv.slice(2);
for (const path of paths) {
  const workbook = await SpreadsheetFile.importXlsx(await FileBlob.load(path));
  const summary = await workbook.inspect({
    kind: "workbook,sheet,formula",
    include: "id,name,formula",
    maxChars: 5000,
    maxResults: 40,
  });
  process.stdout.write(JSON.stringify({ path, summary: summary.ndjson }) + "\n");
}
