import http from 'k6/http';
import { check, sleep } from 'k6';

export const options = {
  stages: [
    { duration: '10s', target: 50 },  // Ramp up to 50 active swipers
    { duration: '30s', target: 200 }, // Peak pressure of 200 users swiping
    { duration: '10s', target: 0 },   // Cool down
  ],
};

const BASE_URL = 'http://localhost:8085/api/v1';

export default function () {
  const userNum = __VU; // Virtual User ID (starts at 1)
  const isUserA = userNum % 2 === 0;
  
  // Simulated authentication token using the mock bypass
  const params = {
    headers: {
      'Content-Type': 'application/json',
      'Authorization': `Bearer mock_token_user_usr_${userNum}`,
    },
  };

  // Determine randomly whether this VU iteration should trigger request profiling (e.g., 1% chance)
  const shouldProfile = Math.random() < 0.01;
  const profilingSecret = __ENV.PROFILING_SECRET || 'true';
  const profileQ = shouldProfile ? `?profile=${profilingSecret}` : '';

  // Step 0: Register/Login the user so they exist in the database.
  // This ensures GET /candidates doesn't return 404.
  const registerPayload = JSON.stringify({
    puuid: `puuid_user_${userNum}`,
    riot_id_name: `User_${userNum}`,
    riot_id_tag: 'NA1'
  });
  
  let registerRes = http.post(`${BASE_URL}/auth/token${profileQ}`, registerPayload, {
    headers: { 'Content-Type': 'application/json' }
  });
  
  check(registerRes, {
    'user registered or logged in': (r) => r.status === 200
  });

  // Step 1: Query candidates
  let res = http.get(`${BASE_URL}/candidates${profileQ}`, params);
  check(res, { 'candidates fetched': (r) => r.status === 200 });
  sleep(1);

  // Step 2: Swipe Actions
  // Pair userNum with userNum + 1 (if A) or userNum - 1 (if B)
  const partnerNum = isUserA ? userNum + 1 : userNum - 1;
  const partnerId = `usr_${partnerNum}`;
  
  let swipeRes = http.post(`${BASE_URL}/swipes${profileQ}`, JSON.stringify({
    target_user_id: partnerId,
    action: 'LIKE'
  }), params);

  check(swipeRes, { 'swipe response ok': (r) => r.status === 200 });

  if (swipeRes.status === 200) {
    const parsedSwipe = JSON.parse(swipeRes.body);
    const matched = parsedSwipe.matched;
    const proposalId = parsedSwipe.proposal_id;

    if (matched && proposalId) {
      // Step 3: Complete handshake within 30-second limit
      sleep(1); // Simulate human delay
      let respondRes = http.post(`${BASE_URL}/match/respond${profileQ}`, JSON.stringify({
        proposal_id: proposalId,
        action: 'ACCEPT'
      }), params);

      check(respondRes, {
        'handshake completed successfully': (r) => r.status === 200 || r.status === 202
      });
    }
  }
  
  sleep(2);
}
