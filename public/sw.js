// public/sw.js

// Listen for notifications sent by Apple/Google Push Gateways
self.addEventListener('push', (event) => {
    if (!event.data) return;
    
    const data = event.data.json();
    
    event.waitUntil(
        self.clients.matchAll({ type: 'window', includeUncontrolled: true }).then((clientList) => {
            const isAppVisible = clientList.some(client => client.visibilityState === 'visible');
            
            if (isAppVisible) {
                // If user is actively looking at Linder in their browser, 
                // send an in-app message to trigger the 30-second modal UI instantly.
                clientList.forEach((client) => {
                    client.postMessage({
                        type: 'MATCH_PROPOSED',
                        proposal_id: data.proposal_id,
                        expires_in: 30
                    });
                });
            } else {
                // If user is offline, on their home screen, or in another app,
                // present a system notification.
                return self.registration.showNotification('Linder: Match Found!', {
                    body: 'A player from your last match wants to connect. You have 30 seconds to join!',
                    icon: '/icon-192.png',
                    tag: 'match-proposal', // Prevents double alerting
                    data: { proposal_id: data.proposal_id }
                });
            }
        })
    );
});

// React when user taps the native system notification banner
self.addEventListener('notificationclick', (event) => {
    event.notification.close();
    const proposalId = event.notification.data.proposal_id;
    const targetUrl = `/match/accept?id=${proposalId}`;

    event.waitUntil(
        self.clients.matchAll({ type: 'window' }).then((clientList) => {
            // Find existing open tab and redirect
            for (const client of clientList) {
                if (client.url && 'focus' in client) {
                    client.postMessage({ type: 'NAVIGATE', url: targetUrl });
                    return client.focus();
                }
            }
            // If no tabs are open, boot a new window directly to acceptance screen
            if (self.clients.openWindow) {
                return self.clients.openWindow(targetUrl);
            }
        })
    );
});
