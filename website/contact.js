// Pre-fill the message when arriving from a vacancy page (?job=<id>&title=<title>)
(() => {
  const p = new URLSearchParams(window.location.search);
  const jobTitle = p.get('title');
  if (!jobTitle) return;
  const msg = document.querySelector('#contactForm textarea[name="message"]');
  if (msg && !msg.value) {
    const lang = localStorage.getItem('gsp_lang') || 'nl';
    msg.value = lang === 'nl'
      ? `Ik wil graag solliciteren op de vacature: ${jobTitle} (ref: ${p.get('job') || '-'})\n\n`
      : `I would like to apply for the vacancy: ${jobTitle} (ref: ${p.get('job') || '-'})\n\n`;
    msg.focus();
  }
})();
