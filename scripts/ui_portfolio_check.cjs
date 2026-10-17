const {chromium}=require(process.env.JARVIS_PLAYWRIGHT || "playwright");
const fs=require("fs");
(async()=>{
 const browser=await chromium.launch({channel:"msedge",headless:true});
 try{
  const page=await browser.newPage({viewport:{width:1440,height:1000}});
  const errors=[];page.on("pageerror",e=>errors.push(e.message));
  await page.goto("http://127.0.0.1:4173");
  await page.locator('[data-project="jarvis"]').first().click();
  await page.getByText("A complete Windows handoff",{exact:true}).waitFor();
  const text=await page.locator("#project-dialog").innerText();
  if(!text.includes("Working local Windows application"))throw Error("Project status did not update");
  await page.screenshot({path:"data/portfolio-jarvis-dialog.png",fullPage:true});
  await page.keyboard.press("Escape");
  await page.goto("http://127.0.0.1:4173/experiments/jarvis/case-study.html");
  await page.getByText("WORKING LOCAL WINDOWS APP",{exact:true}).waitFor();
  await page.screenshot({path:"data/portfolio-case-study.png",fullPage:true});
  await page.setViewportSize({width:390,height:844});
  const overflow=await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth);
  await page.screenshot({path:"data/portfolio-case-mobile.png",fullPage:true});
  if(errors.length||overflow)throw Error(JSON.stringify({errors,overflow}));
  console.log(JSON.stringify({pageErrors:errors,mobileOverflow:overflow,workingAppNarrative:true}));
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
