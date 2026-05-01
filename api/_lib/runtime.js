export function getEnv(name, altName) {
  return process.env[name] || (altName ? process.env[altName] : "") || "";
}

export function requireEnv(name, altName) {
  const val = getEnv(name, altName);
  if (!val) {
    const err = new Error(`Missing required environment variable: ${name}`);
    err.status = 500;
    throw err;
  }
  return val;
}