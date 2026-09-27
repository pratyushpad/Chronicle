// LOCAL-ONLY: mint an Auth.js (NextAuth v5) session cookie for screenshotting signed-in pages
// of a LOCAL build started with the same throwaway AUTH_SECRET. Never use a production secret.
// usage: LOCAL_AUTH_SECRET=... node mint-session.mjs <web_dir> <email> [name]
// prints a Playwright cookie JSON array for http://localhost
const [webDir, email, name = "Local Tester"] = process.argv.slice(2);
const secret = process.env.LOCAL_AUTH_SECRET;
if (!secret || !secret.startsWith("local-")) {
  console.error("LOCAL_AUTH_SECRET must be set and start with 'local-' (refusing to mint with a real secret)");
  process.exit(1);
}
const { encode } = await import(`${webDir}/node_modules/@auth/core/jwt.js`);
const cookieName = "authjs.session-token";
const token = {
  name, email, picture: null, sub: "local-test-user",
  provider: "google", providerAccountId: "local-test-user",
};
const value = await encode({ token, secret, salt: cookieName, maxAge: 60 * 60 * 24 });
console.log(JSON.stringify([{ name: cookieName, value, domain: "localhost", path: "/", httpOnly: true, sameSite: "Lax" }]));
