import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const MATCH_STOP_WORDS = new Set([
  'club', 'atletico', 'atlético', 'ca', 'cd', 'cf', 'fc', 'sp', 'sc', 'ad',
  'de', 'la', 'del', 'el', 'los', 'las', 'da', 'do', 'dos', 'das', 'e',
  'deportivo', 'deportiva', 'sport', 'social', 'asociacion', 'asociación'
]);

export function normalizeTeam(name) {
  if (!name) return '';
  let n = name.toLowerCase().trim();
  const prefixes = ['club atlético ', 'club atletico ', 'ca ', 'cd ', 'cf ', 'fc ', 'ad ', 'sc '];
  for (const prefix of prefixes) {
    if (n.startsWith(prefix)) {
      n = n.slice(prefix.length);
      break;
    }
  }
  return n.replace(/[^a-z0-9]/gi, '');
}

export function cleanNameForMatching(text) {
  if (!text) return '';
  return text
    .normalize('NFKD')
    .replace(/[\u0300-\u036f]/g, '')
    .toLowerCase()
    .replace(/[^a-z0-9\s]/g, ' ')
    .trim()
    .replace(/\s+/g, ' ');
}

export function extractTeamTokens(teamName) {
  const clean = cleanNameForMatching(teamName);
  const words = clean.split(' ');
  let tokens = words.filter(w => !MATCH_STOP_WORDS.has(w) && w.length >= 3);
  if (!tokens.length) {
    tokens = words.filter(w => w.length >= 3);
  }
  return { tokens, clean };
}

export function getLeagueBadgeInfo(leagueName, countryName) {
  const lg = (leagueName || '').toLowerCase();
  const cc = (countryName || '').toLowerCase();
  const full = `${cc} ${lg}`;

  if (lg.includes('nations league') || lg.includes('uefa nations league') || full.includes('nations league')) {
    return { badgeClass: 'badge-nationsleague', cleanLeague: 'UEFA Nations League', cleanCountry: 'Europe' };
  }
  if (lg.includes('libertadores') || full.includes('libertadores')) {
    return { badgeClass: 'badge-libertadores', cleanLeague: 'Copa Libertadores', cleanCountry: 'South America' };
  }
  if (lg.includes('sudamericana') || full.includes('sudamericana')) {
    return { badgeClass: 'badge-sudamericana', cleanLeague: 'Copa Sudamericana', cleanCountry: 'South America' };
  }
  if (lg.includes('copa do brasil') || lg.includes('copa brasil') || full.includes('copa do brasil')) {
    return { badgeClass: 'badge-brazil', cleanLeague: 'Copa do Brasil', cleanCountry: 'Brazil' };
  }
  if (lg.includes('copa argentina') || full.includes('copa argentina')) {
    return { badgeClass: 'badge-argentina', cleanLeague: 'Copa Argentina', cleanCountry: 'Argentina' };
  }
  if (['argentina', 'arg', 'clausura', 'apertura', 'liga profesional'].some(k => full.includes(k))) {
    return { badgeClass: 'badge-argentina', cleanLeague: leagueName, cleanCountry: 'Argentina' };
  }

  const isBrazil = ['bra', 'brazil', 'brasil'].some(k => cc.includes(k)) || ['brazil', 'brasil', 'brasileir'].some(k => lg.includes(k));
  if (isBrazil && ['série a', 'serie a', 'brasileirão', 'brasileiro', 'paulistão', 'carioca', 'copa do brasil'].some(k => lg.includes(k))) {
    return { badgeClass: 'badge-brazil', cleanLeague: 'Série A', cleanCountry: 'Brazil' };
  }

  return { badgeClass: 'badge-default', cleanLeague: leagueName, cleanCountry: countryName || 'LATAM' };
}

export function isTargetMatch(leagueName, countryName) {
  const lg = (leagueName || '').toLowerCase();
  const cc = (countryName || '').toLowerCase();
  const full = `${cc} ${lg}`;

  // Explicitly exclude Copa Paulista
  if (lg.includes('copa paulista') || full.includes('copa paulista')) return false;

  // UEFA Nations League matches (e.g. Germany vs Netherlands, France vs Italy, etc.)
  if (lg.includes('nations league') || lg.includes('uefa nations league') || full.includes('nations league')) {
    return true;
  }

  // Reject European and non-target countries
  const nonTargetCountries = ['ita', 'italy', 'italia', 'esp', 'spain', 'españa', 'eng', 'england', 'ger', 'germany', 'fra', 'france', 'por', 'portugal', 'ned', 'saudi', 'mex'];
  if (nonTargetCountries.some(k => cc.includes(k))) return false;

  if (lg.includes('libertadores') || full.includes('libertadores')) return true;
  if (lg.includes('sudamericana') || full.includes('sudamericana')) return true;
  if (lg.includes('copa argentina') || full.includes('copa argentina')) return true;
  if (lg.includes('copa do brasil') || lg.includes('copa brasil') || full.includes('copa do brasil')) return true;

  if (cc.includes('arg') || full.includes('argentina')) {
    if (['liga profesional', 'copa argentina', 'clausura', 'apertura', 'supercopa', 'trofeo de campeones', 'copa de la liga'].some(k => lg.includes(k))) {
      return true;
    }
  }

  const isBrazil = ['bra', 'brazil', 'brasil'].some(k => cc.includes(k)) || ['brazil', 'brasil', 'brasileir'].some(k => lg.includes(k));
  if (isBrazil) {
    if (['série a', 'serie a', 'brasileir', 'paulistão', 'copa do brasil', 'carioca'].some(k => lg.includes(k))) {
      return true;
    }
  }

  return false;
}

export function isSharedTournament(leagueName, countryName = '') {
  const full = `${leagueName || ''} ${countryName || ''}`.toLowerCase();
  const sharedKeywords = ['libertadores', 'sudamericana', 'nations league', 'recopa'];
  return sharedKeywords.some(k => full.includes(k));
}

export function getCategorizedChannels(leagueName, countryName, existingArg = null, existingBra = null) {
  const shared = isSharedTournament(leagueName, countryName);
  const lg = (leagueName || '').toLowerCase();
  const cc = (countryName || '').toLowerCase();
  const full = `${cc} ${lg}`;

  let channels_arg = [];
  let channels_bra = [];

  if (shared) {
    if (Array.isArray(existingArg) && existingArg.length > 0) {
      channels_arg = [...existingArg];
    } else {
      channels_arg = ['ESPN Premium', 'Fox Sports', 'Star+', 'Disney+', 'DSports', 'TyC Sports'];
    }

    if (Array.isArray(existingBra) && existingBra.length > 0) {
      channels_bra = [...existingBra];
    } else {
      channels_bra = ['Globo', 'SporTV', 'Premiere', 'CazéTV', 'Paramount+'];
    }

    return {
      is_shared_league: true,
      channels_arg,
      channels_bra
    };
  }

  // Domestic Leagues: Show ONLY single relevant country channels
  const isBra = full.includes('brazil') || full.includes('brasil') || cc.includes('bra') || lg.includes('série a') || lg.includes('serie a') || lg.includes('copa do brasil') || lg.includes('paulistão');

  if (isBra) {
    if (Array.isArray(existingBra) && existingBra.length > 0) {
      channels_bra = [...existingBra];
    } else {
      channels_bra = ['Premiere', 'Globo', 'SporTV', 'CazéTV'];
    }
    channels_arg = [];
    return {
      is_shared_league: false,
      channels_arg: [],
      channels_bra
    };
  }

  // Domestic Argentina
  if (Array.isArray(existingArg) && existingArg.length > 0) {
    channels_arg = [...existingArg];
  } else {
    channels_arg = ['ESPN Premium', 'TNT Sports', 'TyC Sports', 'Disney+'];
  }
  channels_bra = [];

  return {
    is_shared_league: false,
    channels_arg,
    channels_bra: []
  };
}

export function renderChannelsHtml(m) {
  const isShared = (m.is_shared_league !== undefined) ? Boolean(m.is_shared_league) : isSharedTournament(m.league, m.country);
  let channelsArg = Array.isArray(m.channels_arg) ? m.channels_arg : [];
  let channelsBra = Array.isArray(m.channels_bra) ? m.channels_bra : [];

  if (channelsArg.length === 0 && channelsBra.length === 0) {
    const cat = getCategorizedChannels(m.league, m.country);
    channelsArg = cat.channels_arg;
    channelsBra = cat.channels_bra;
  }

  const argSpans = channelsArg.map(c => `<span class="channel-tag tag-arg">${c}</span>`).join(' ');
  const braSpans = channelsBra.map(c => `<span class="channel-tag tag-bra">${c}</span>`).join(' ');

  if (isShared) {
    const leftCol = `<div class="channels-col"><span class="country-tag-hdr">🇦🇷 ARG:</span><div class="channel-pill-stack">${argSpans || '<span class="channel-tag">TBD</span>'}</div></div>`;
    const rightCol = `<div class="channels-col"><span class="country-tag-hdr">🇧🇷 BRA:</span><div class="channel-pill-stack">${braSpans || '<span class="channel-tag">TBD</span>'}</div></div>`;
    return `<div style="display:flex; gap:14px; align-items:flex-start;">${leftCol}${rightCol}</div>`;
  }

  // Domestic League
  if (channelsArg.length > 0) {
    return `<div class="channels-col"><span class="country-tag-hdr">🇦🇷 ARG:</span><div class="channel-pill-stack">${argSpans}</div></div>`;
  } else if (channelsBra.length > 0) {
    return `<div class="channels-col"><span class="country-tag-hdr">🇧🇷 BRA:</span><div class="channel-pill-stack">${braSpans}</div></div>`;
  }

  return '<span class="channel-tag">TBD</span>';
}

export function getChannelsForMatch(leagueName, countryName) {
  const lg = (leagueName || '').toLowerCase();
  const cc = (countryName || '').toLowerCase();
  const full = `${cc} ${lg}`;

  if (full.includes('nations league') || lg.includes('nations league')) {
    return ['ESPN', 'Fox Sports', 'Star+', 'UEFA.tv'];
  } else if (full.includes('libertadores')) {
    return ['ESPN', 'Fox Sports', 'Star+', 'Globo'];
  } else if (full.includes('sudamericana')) {
    return ['ESPN 3', 'Star+', 'DSports', 'Paramount+'];
  } else if (full.includes('argentina') || cc.includes('arg') || lg.includes('liga profesional') || lg.includes('copa argentina')) {
    return ['ESPN Premium', 'TNT Sports', 'TyC Sports', 'Star+'];
  } else if (full.includes('brazil') || full.includes('brasil') || cc.includes('bra') || lg.includes('série a') || lg.includes('serie a') || lg.includes('paulista') || lg.includes('copa do brasil') || lg.includes('copa paulista')) {
    return ['Premiere', 'Globo', 'SporTV', 'CazéTV'];
  }
  return ['TNT Sports', 'ESPN Premium'];
}

export function calculateStatus(matchDt, started = false, finished = false, cancelled = false, scoreStr = null, liveTime = null) {
  const cleanScore = (scoreStr && scoreStr.trim() && !['-', 'vs', 'undefined', 'null', 'None'].includes(scoreStr.trim())) ? scoreStr.trim() : null;

  if (cancelled) return { text: 'CANCELLED', statusClass: 'status-cancelled' };
  if (finished) {
    const text = cleanScore ? `FINISHED (${cleanScore})` : 'FINISHED';
    return { text, statusClass: 'status-finished' };
  }
  if (started) {
    const minDisp = liveTime ? liveTime.trim() : 'LIVE';
    let text = (minDisp !== 'LIVE') ? `LIVE 🔴 ${minDisp}` : 'LIVE 🔴';
    if (cleanScore) text += ` (${cleanScore})`;
    return { text, statusClass: 'status-live' };
  }
  if (!matchDt) return { text: 'SCHEDULED', statusClass: 'status-scheduled' };

  const now = new Date();
  const dt = (matchDt instanceof Date) ? matchDt : new Date(matchDt);
  if (isNaN(dt.getTime())) return { text: 'SCHEDULED', statusClass: 'status-scheduled' };

  const diffSec = (now.getTime() - dt.getTime()) / 1000;

  if (diffSec > 7200) {
    // Over 2 hours since kickoff -> Finished
    const text = cleanScore ? `FINISHED (${cleanScore})` : 'FINISHED';
    return { text, statusClass: 'status-finished' };
  } else if (diffSec >= 0) {
    // 0 to 120 minutes since kickoff -> Live
    const elapsedMins = Math.max(1, Math.floor(diffSec / 60));
    let minDisp = `${elapsedMins}'`;
    if (liveTime) {
      minDisp = liveTime;
    } else if (elapsedMins <= 45) {
      minDisp = `${elapsedMins}'`;
    } else if (elapsedMins <= 60) {
      minDisp = 'HT';
    } else if (elapsedMins <= 105) {
      minDisp = `${elapsedMins - 15}'`;
    } else {
      minDisp = "90+'";
    }
    let text = `LIVE 🔴 ${minDisp}`;
    if (cleanScore) text += ` (${cleanScore})`;
    return { text, statusClass: 'status-live' };
  } else if (-diffSec <= 3600) {
    // Starts within next 60 minutes -> Soon
    const mins = Math.max(1, Math.floor(-diffSec / 60));
    return { text: `SOON (${mins}m)`, statusClass: 'status-soon' };
  } else {
    return { text: 'SCHEDULED', statusClass: 'status-scheduled' };
  }
}

export function getMatchKickoffDate(m, fallbackDateStr) {
  if (!m || typeof m !== 'object') return null;

  if (m.kickoff_utc) {
    const d = new Date(m.kickoff_utc);
    if (!isNaN(d.getTime())) return d;
  }
  if (m.match_dt) {
    const d = (m.match_dt instanceof Date) ? m.match_dt : new Date(m.match_dt);
    if (!isNaN(d.getTime())) return d;
  }
  if (m.status && typeof m.status === 'object' && m.status.utcTime) {
    const d = new Date(m.status.utcTime);
    if (!isNaN(d.getTime())) return d;
  }

  const dateStr = m.match_date || fallbackDateStr;
  if (!dateStr || typeof dateStr !== 'string') return null;

  const mTime = m.morocco_time;
  const lTime = m.local_time;

  if (mTime && mTime !== 'TBD' && mTime.includes(':')) {
    const [mh, mm] = mTime.split(':').map(Number);
    const [y, mo, d] = dateStr.split('-').map(Number);
    if (!isNaN(mh) && !isNaN(mm) && !isNaN(y) && !isNaN(mo) && !isNaN(d)) {
      let dtUtc = new Date(Date.UTC(y, mo - 1, d, mh, mm, 0));
      if (lTime && lTime !== 'TBD' && lTime.includes(':')) {
        const lh = parseInt(lTime.split(':')[0], 10);
        if (!isNaN(lh) && mh < lh) {
          // Crosses midnight UTC
          dtUtc = new Date(dtUtc.getTime() + 86400000);
        }
      }
      return dtUtc;
    }
  }

  if (lTime && lTime !== 'TBD' && lTime.includes(':')) {
    const [lh, lm] = lTime.split(':').map(Number);
    const [y, mo, d] = dateStr.split('-').map(Number);
    if (!isNaN(lh) && !isNaN(lm) && !isNaN(y) && !isNaN(mo) && !isNaN(d)) {
      // Local time is GMT-3 -> add 3 hours for UTC
      return new Date(Date.UTC(y, mo - 1, d, lh + 3, lm, 0));
    }
  }

  return null;
}

export function rewriteCdnImageUrl(url) {
  if (!url) return url;
  if (url.startsWith('./banners/') || url.startsWith('banners/') || url.startsWith('/banners/') || url.includes('aspijik07.github.io') || url.includes('/banners/')) {
    return url;
  }
  const bases = [
    'https://www.zerozero.com.ar', 'http://www.zerozero.com.ar',
    'https://zerozero.com.ar', 'http://zerozero.com.ar',
    'https://www.ogol.com.br', 'http://www.ogol.com.br',
    'https://ogol.com.br', 'http://ogol.com.br',
    'https://www.zerozero.pt', 'http://www.zerozero.pt',
    'https://zerozero.pt', 'http://zerozero.pt'
  ];
  for (const b of bases) {
    if (url.startsWith(b)) {
      return 'https://cdn-img.staticzz.com' + url.slice(b.length);
    }
  }
  return url;
}

export function calculateMoroccoTime(localTimeStr) {
  if (!localTimeStr || typeof localTimeStr !== 'string') return 'TBD';
  const clean = localTimeStr.trim();
  const match = clean.match(/^(\d{1,2}):(\d{2})$/);
  if (!match) return 'TBD';
  const h = parseInt(match[1], 10);
  const m = parseInt(match[2], 10);
  if (isNaN(h) || isNaN(m)) return 'TBD';
  // Latam local time is GMT-3. GMT-3 to GMT 0 is strictly +3 Hours.
  const moroccoH = (h + 3) % 24;
  return `${String(moroccoH).padStart(2, '0')}:${String(m).padStart(2, '0')}`;
}

export function formatMatchTimes(matchDt) {
  if (!matchDt || isNaN(matchDt.getTime())) {
    return { localTime: 'TBD', moroccoTime: 'TBD' };
  }
  // Morocco timezone is strictly GMT 0 (UTC+0 without unwanted +1h offset)
  const moroccoTime = matchDt.toLocaleTimeString('en-GB', {
    timeZone: 'UTC',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false
  });
  // Latam local time is strictly GMT-3
  const localTime = matchDt.toLocaleTimeString('en-GB', {
    timeZone: 'America/Argentina/Buenos_Aires',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false
  });
  return { localTime, moroccoTime };
}

export function isValidFixture(m, targetDate = null) {
  if (!m || typeof m !== 'object') return false;

  const home = (m.home_team || '').trim();
  const away = (m.away_team || '').trim();
  const league = (m.league || m.league_name || '').trim();

  if (!home || !away || !league) return false;

  const invalidPlaceholders = new Set([
    'tbd', 'tba', 'home', 'away', 'unknown', 'n/a', 'na', 'none', 'null', '?', '--',
    'team a', 'team b', 'team 1', 'team 2', 'time a', 'time b', 'tbd vs tbd',
    'a determinar', 'por definir', 'indefinido'
  ]);

  const unconfirmedKeywords = [
    'tbd', 'tba', 'postponed', 'pospuesto', 'postergado', 'adiado', 'cancelled',
    'canceled', 'cancelado', 'suspended', 'suspenso', 'interrupted', 'abandoned',
    'delayed', 'retardado', 'aplazado', 'unconfirmed', 'sin confirmar',
    'por definir', 'a definir', 'indefinido'
  ];

  const homeLower = home.toLowerCase();
  const awayLower = away.toLowerCase();
  const leagueLower = league.toLowerCase();

  if (invalidPlaceholders.has(homeLower) || invalidPlaceholders.has(awayLower) || invalidPlaceholders.has(leagueLower)) {
    return false;
  }
  if (homeLower === 'tbd vs tbd' || awayLower === 'tbd vs tbd') {
    return false;
  }

  // Reject identical teams
  const hNorm = normalizeTeam(home);
  const aNorm = normalizeTeam(away);
  if (hNorm && aNorm && hNorm === aNorm) return false;

  // Strictly exclude Copa Paulista
  if (leagueLower.includes('copa paulista')) return false;

  // Reject postponed/cancelled/unconfirmed statuses
  const statusText = (m.status_text || m.status || '').toLowerCase();
  const statusClass = (m.status_class || '').toLowerCase();
  for (const kw of unconfirmedKeywords) {
    if (statusText.includes(kw) || statusClass.includes(kw)) {
      return false;
    }
  }
  if (m.cancelled || m.postponed) return false;

  // Kickoff time check: must have confirmed HH:MM
  const timeCandidates = [m.local_time, m.morocco_time, m.start_time, m.time_str, m.time_val]
    .filter(t => typeof t === 'string' && t.trim().length > 0)
    .map(t => t.trim());

  if (!timeCandidates.length) return false;
  for (const t of timeCandidates) {
    const tLow = t.toLowerCase();
    if (invalidPlaceholders.has(tLow) || unconfirmedKeywords.some(kw => tLow.includes(kw))) {
      return false;
    }
  }

  const hasConfirmedTime = timeCandidates.some(t => /^\d{1,2}:\d{2}$/.test(t));
  if (!hasConfirmedTime) return false;

  // Reject 00:00 midnight placeholder in local time when not live/finished
  const localTime = (m.local_time || '').trim();
  const isLive = Boolean(m.is_live) || statusText.includes('live');
  const isFinished = statusText.includes('finished') || statusClass === 'status-finished';
  if (localTime === '00:00' && !isLive && !isFinished) {
    return false;
  }

  // Cross-check UTC timestamps to ensure matches belong strictly to today's and tomorrow's official 24-hour windows
  const now = new Date();
  const todayStartUtc = new Date(Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), now.getUTCDate(), 0, 0, 0));
  const tomorrowEndUtc = new Date(todayStartUtc.getTime() + 2 * 86400000);
  const pad = n => String(n).padStart(2, '0');
  const todayStr = `${todayStartUtc.getUTCFullYear()}-${pad(todayStartUtc.getUTCMonth() + 1)}-${pad(todayStartUtc.getUTCDate())}`;
  const tomorrowDate = new Date(todayStartUtc.getTime() + 86400000);
  const tomorrowStr = `${tomorrowDate.getUTCFullYear()}-${pad(tomorrowDate.getUTCMonth() + 1)}-${pad(tomorrowDate.getUTCDate())}`;

  let matchDt = null;
  if (m.match_dt instanceof Date) {
    matchDt = m.match_dt;
  } else if (m.startTimestamp) {
    matchDt = new Date(Number(m.startTimestamp) * 1000);
  } else if (m.timestamp) {
    const ts = Number(m.timestamp);
    matchDt = new Date(ts > 1e11 ? ts : ts * 1000);
  } else if (m.utcTime || m.utc_time) {
    const rawUtc = m.utcTime || m.utc_time;
    const parsed = Date.parse(rawUtc);
    if (!isNaN(parsed)) matchDt = new Date(parsed);
  }

  if (matchDt && !isNaN(matchDt.getTime())) {
    // Check if strictly within [todayStartUtc - 3.5h, tomorrowEndUtc)
    if (matchDt.getTime() < (todayStartUtc.getTime() - 3.5 * 3600000) || matchDt.getTime() >= tomorrowEndUtc.getTime()) {
      return false;
    }
  }

  // Check match_date string if present
  const matchDate = (m.match_date || m.date || '').trim();
  if (matchDate && /^\d{4}-\d{2}-\d{2}$/.test(matchDate)) {
    if (matchDate !== todayStr && matchDate !== tomorrowStr) {
      return false;
    }
  }

  const dayLabel = (m.day_label || m.day || '').toLowerCase();
  if (['yesterday', 'past', 'ontem', 'ayer', 'historico', 'anterior'].includes(dayLabel)) {
    return false;
  }

  return true;
}

export function generateBannerUrl(homeName, awayName) {
  const hNorm = normalizeTeam(homeName);
  const aNorm = normalizeTeam(awayName);
  return `./banners/${hNorm}_${aNorm}.jpg`;
}

export async function fetchFotmobMatches(targetDate, dayLabel) {
  const matches = [];
  const yyyy = targetDate.getUTCFullYear();
  const mm = String(targetDate.getUTCMonth() + 1).padStart(2, '0');
  const dd = String(targetDate.getUTCDate()).padStart(2, '0');
  const dateFotmob = `${yyyy}${mm}${dd}`;
  const url = `https://www.fotmob.com/api/data/matches?date=${dateFotmob}`;

  try {
    const res = await fetch(url, {
      headers: {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
        'Accept': 'application/json, text/plain, */*',
        'Referer': 'https://www.fotmob.com/'
      },
      signal: AbortSignal.timeout(8000)
    });
    if (!res.ok) return matches;
    const data = await res.json();
    if (!data || !Array.isArray(data.leagues)) return matches;

    for (const lg of data.leagues) {
      const lgName = lg.name || '';
      const lgCcode = lg.ccode || '';

      if (isTargetMatch(lgName, lgCcode)) {
        const { badgeClass, cleanLeague, cleanCountry } = getLeagueBadgeInfo(lgName, lgCcode);

        for (const m of (lg.matches || [])) {
          const st = m.status || {};
          const utcTime = st.utcTime;
          const matchDt = utcTime ? new Date(utcTime) : null;

          const { localTime, moroccoTime: mTime } = formatMatchTimes(matchDt);

          const started = Boolean(st.started);
          const finished = Boolean(st.finished);
          const cancelled = Boolean(st.cancelled);
          const scoreStr = st.scoreStr || null;
          const liveTime = typeof st.liveTime === 'object' && st.liveTime ? st.liveTime.short : null;

          const { text: statusText, statusClass } = calculateStatus(matchDt, started, finished, cancelled, scoreStr, liveTime);

          const home = m.home || {};
          const away = m.away || {};
          const homeName = home.name || 'Home';
          const awayName = away.name || 'Away';
          const homeId = home.id;
          const awayId = away.id;

          const homeLogo = homeId ? `https://images.fotmob.com/image_resources/logo/teamlogo/${homeId}.png` : '';
          const awayLogo = awayId ? `https://images.fotmob.com/image_resources/logo/teamlogo/${awayId}.png` : '';

          const bannerUrl = generateBannerUrl(homeName, awayName);

            const cat = getCategorizedChannels(cleanLeague, cleanCountry);
            const fixtureItem = {
              day: dayLabel,
              match_date: `${yyyy}-${mm}-${dd}`,
              league: cleanLeague,
              country: cleanCountry,
              badge_class: badgeClass,
              home_team: homeName,
              away_team: awayName,
              home_logo: homeLogo,
              away_logo: awayLogo,
              local_time: localTime,
              morocco_time: mTime,
              status_text: statusText,
              status_class: statusClass,
              kickoff_utc: matchDt ? matchDt.toISOString() : null,
              is_shared_league: cat.is_shared_league,
              channels_arg: cat.channels_arg,
              channels_bra: cat.channels_bra,
              channels: (cat.channels_arg.length > 0 || cat.channels_bra.length > 0) ? [...cat.channels_arg, ...cat.channels_bra] : getChannelsForMatch(cleanLeague, cleanCountry),
              banner_url: bannerUrl,
            banner_title: `${homeName} vs ${awayName}`,
            banner_source_site: 'github.io',
            has_scraped_banner: true,
            source: 'fotmob',
            match_dt: matchDt
          };

          if (isValidFixture(fixtureItem, targetDate)) {
            matches.push(fixtureItem);
          }
        }
      }
    }
  } catch (err) {
    console.warn('Fotmob fetch notice:', err.message);
  }

  return matches;
}

export async function fetchSofascoreMatches(targetDate, dayLabel) {
  const matches = [];
  const yyyy = targetDate.getUTCFullYear();
  const mm = String(targetDate.getUTCMonth() + 1).padStart(2, '0');
  const dd = String(targetDate.getUTCDate()).padStart(2, '0');
  const dateIso = `${yyyy}-${mm}-${dd}`;
  const url = `https://api.sofascore.com/api/v1/sport/football/scheduled-events/${dateIso}`;

  try {
    const res = await fetch(url, {
      headers: {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
        'Accept': '*/*',
        'Referer': 'https://www.sofascore.com/'
      },
      signal: AbortSignal.timeout(8000)
    });
    if (!res.ok) return matches;
    const data = await res.json();
    if (!data || !Array.isArray(data.events)) return matches;

    for (const ev of data.events) {
      const tournament = ev.tournament || {};
      const tName = tournament.name || '';
      const catName = tournament.category ? tournament.category.name : '';

      if (isTargetMatch(tName, catName)) {
        const { badgeClass, cleanLeague, cleanCountry } = getLeagueBadgeInfo(tName, catName);
        const ts = ev.startTimestamp;
        const matchDt = ts ? new Date(ts * 1000) : null;

        const { localTime, moroccoTime: mTime } = formatMatchTimes(matchDt);

        const stObj = ev.status || {};
        const stType = stObj.type || '';
        const finished = (stType === 'finished');
        const started = (stType === 'inprogress');
        const cancelled = (stType === 'canceled');

        const hScore = ev.homeScore ? ev.homeScore.current : null;
        const aScore = ev.awayScore ? ev.awayScore.current : null;
        const scoreStr = (hScore != null && aScore != null) ? `${hScore} - ${aScore}` : null;

        const { text: statusText, statusClass } = calculateStatus(matchDt, started, finished, cancelled, scoreStr);

        const homeTeam = ev.homeTeam || {};
        const awayTeam = ev.awayTeam || {};
        const homeName = homeTeam.name || 'Home';
        const awayName = awayTeam.name || 'Away';
        const homeId = homeTeam.id;
        const awayId = awayTeam.id;

        const homeLogo = homeId ? `https://api.sofascore.app/api/v1/team/${homeId}/image` : '';
        const awayLogo = awayId ? `https://api.sofascore.app/api/v1/team/${awayId}/image` : '';

        const bannerUrl = generateBannerUrl(homeName, awayName);

        const cat = getCategorizedChannels(cleanLeague, cleanCountry);
        const fixtureItem = {
          day: dayLabel,
          match_date: `${yyyy}-${mm}-${dd}`,
          league: cleanLeague,
          country: cleanCountry,
          badge_class: badgeClass,
          home_team: homeName,
          away_team: awayName,
          home_logo: homeLogo,
          away_logo: awayLogo,
          local_time: localTime,
          morocco_time: mTime,
          status_text: statusText,
          status_class: statusClass,
          kickoff_utc: matchDt ? matchDt.toISOString() : null,
          is_shared_league: cat.is_shared_league,
          channels_arg: cat.channels_arg,
          channels_bra: cat.channels_bra,
          channels: (cat.channels_arg.length > 0 || cat.channels_bra.length > 0) ? [...cat.channels_arg, ...cat.channels_bra] : getChannelsForMatch(cleanLeague, cleanCountry),
          banner_url: bannerUrl,
          banner_title: `${homeName} vs ${awayName}`,
          banner_source_site: 'github.io',
          has_scraped_banner: true,
          source: 'sofascore',
          match_dt: matchDt
        };

        if (isValidFixture(fixtureItem, targetDate)) {
          matches.push(fixtureItem);
        }
      }
    }
  } catch (err) {
    console.warn('Sofascore fetch notice:', err.message);
  }

  return matches;
}

export function loadCachedMatches() {
  const matchesPath = path.join(__dirname, 'matches.json');
  if (fs.existsSync(matchesPath)) {
    try {
      const raw = fs.readFileSync(matchesPath, 'utf8');
      const parsed = JSON.parse(raw);
      const list = parsed.matches || [...(parsed.today || []), ...(parsed.tomorrow || [])];
      return list.map(item => {
        const rawDay = String(item.day || item.day_label || 'Today').toLowerCase();
        const day = (rawDay === 'tomorrow' || rawDay === 'amanha' || rawDay === 'mañana') ? 'tomorrow' : 'today';
        const stText = (item.status_text || item.status || 'SCHEDULED');
        const cleanStText = (stText.toUpperCase() === 'UNDEFINED' || !stText) ? 'SCHEDULED' : stText;
        const stClass = item.status_class || (cleanStText.includes('LIVE') ? 'status-live' : (cleanStText.includes('SOON') ? 'status-soon' : (cleanStText.includes('FINISHED') ? 'status-finished' : 'status-scheduled')));

        const localTime = item.local_time || '20:00';
        const moroccoTime = item.morocco_time ? calculateMoroccoTime(localTime) : '23:00';
        const cat = getCategorizedChannels(item.league, item.country, item.channels_arg, item.channels_bra);

        return {
          day: day,
          day_label: day === 'tomorrow' ? 'Tomorrow' : 'Today',
          match_date: item.match_date,
          league: item.league || 'Liga Profesional',
          country: item.country || 'Argentina',
          badge_class: item.badge_class || getLeagueBadgeInfo(item.league, item.country).badgeClass,
          home_team: item.home_team || '',
          away_team: item.away_team || '',
          home_logo: item.home_logo || '',
          away_logo: item.away_logo || '',
          local_time: localTime,
          morocco_time: moroccoTime,
          status: cleanStText,
          status_text: cleanStText,
          status_class: stClass,
          is_shared_league: cat.is_shared_league,
          channels_arg: cat.channels_arg,
          channels_bra: cat.channels_bra,
          channels: (item.channels && item.channels.length > 0) ? item.channels : (item.all_unique_channels || [...cat.channels_arg, ...cat.channels_bra]),
          banner_url: rewriteCdnImageUrl(item.banner_url || generateBannerUrl(item.home_team, item.away_team)),
          banner_title: item.banner_title || `${item.home_team} vs ${item.away_team}`,
          banner_source_site: item.banner_source_site || 'github.io',
          has_scraped_banner: item.has_scraped_banner ?? true,
          source: 'cache'
        };
      }).filter(m => isValidFixture(m));
    } catch (e) {
      console.warn('Error reading matches.json:', e);
    }
  }
  return [];
}

export async function fetchAllMatches() {
  const now = new Date();
  const combinedMatches = [];

  for (const dayOffset of [0, 1]) {
    const dayLabel = dayOffset === 0 ? 'today' : 'tomorrow';
    const targetDate = new Date(now.getTime() + dayOffset * 86400000);

    const [fmMatches, ssMatches] = await Promise.all([
      fetchFotmobMatches(targetDate, dayLabel),
      fetchSofascoreMatches(targetDate, dayLabel)
    ]);

    combinedMatches.push(...fmMatches, ...ssMatches);
  }

  // Deduplicate matches & validate
  const uniqueMatches = [];
  const seen = new Set();
  for (const m of combinedMatches) {
    if (!isValidFixture(m)) continue;
    const h = normalizeTeam(m.home_team).slice(0, 8);
    const a = normalizeTeam(m.away_team).slice(0, 8);
    const id = `${m.day}_${h}_${a}`;
    if (!seen.has(id)) {
      seen.add(id);
      uniqueMatches.push(m);
    }
  }

  if (uniqueMatches.length === 0) {
    console.log('No live matches found over network or rate limited, falling back to cache');
    return loadCachedMatches();
  }

  // Persist updated matches.json
  try {
    const payload = {
      total_matches: uniqueMatches.length,
      last_updated: new Date().toISOString(),
      matches: uniqueMatches.map(m => ({
        day_label: m.day.charAt(0).toUpperCase() + m.day.slice(1),
        league: m.league,
        country: m.country,
        badge_class: m.badge_class,
        home_team: m.home_team,
        away_team: m.away_team,
        home_logo: m.home_logo,
        away_logo: m.away_logo,
        local_time: m.local_time,
        morocco_time: m.morocco_time,
        status: m.status_text,
        banner_url: m.banner_url,
        banner_title: m.banner_title || `${m.home_team} vs ${m.away_team}`,
        banner_source_site: m.banner_source_site || 'github.io',
        has_scraped_banner: m.has_scraped_banner ?? false,
        is_shared_league: (m.is_shared_league !== undefined) ? Boolean(m.is_shared_league) : isSharedTournament(m.league, m.country),
        channels_arg: m.channels_arg || [],
        channels_bra: m.channels_bra || [],
        channels: m.channels,
        all_unique_channels: m.channels
      }))
    };

    const matchesPath = path.join(__dirname, 'matches.json');
    fs.writeFileSync(matchesPath, JSON.stringify(payload, null, 4), 'utf8');

    const distMatchesPath = path.join(__dirname, 'dist', 'matches.json');
    if (fs.existsSync(path.dirname(distMatchesPath))) {
      fs.writeFileSync(distMatchesPath, JSON.stringify(payload, null, 4), 'utf8');
    }
  } catch (err) {
    console.warn('Could not persist updated matches.json:', err);
  }

  return uniqueMatches;
}
