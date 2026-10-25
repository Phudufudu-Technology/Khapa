// Dumps the prototype's content (data.js) as JSON so data.py is generated, never retyped.
const D = require('./reference/data.js');
process.stdout.write(JSON.stringify(D, null, 1));
