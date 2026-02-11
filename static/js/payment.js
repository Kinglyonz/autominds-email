// Initialize Stripe with the publishable key
const stripe = Stripe('pk_live_51SsZQpRzhH83h3CBAHKRALXbBaeTzPfEwdyiAfB3fk8V3u2a10JerWYLOMSVxjIHAn5i7YYCmtPJnok6BBGdSgxn00jceDXFBu');

/**
 * Stripe Payment Links Configuration
 * Create these in Stripe Dashboard > Payment Links
 * Set success URL to: https://autominds.org/consultation-success.html (for consultation)
 * Set success URL to: https://autominds.org/success.html (for products)
 */
const STRIPE_LINKS = {
    // AutoMinds Studios
    studios_pro: 'https://buy.stripe.com/3cIeVfalz9lOboYd55',
    studios_agency: 'https://buy.stripe.com/00w00lbpD1Tm8cM2qr',
    
    // Consultation - $200 (redirects to Calendly after payment)
    consultation: 'https://buy.stripe.com/5kQeVfgJXgOggJie99',
    
    // SILO Products
    silo_personal: 'https://buy.stripe.com/9B6cN7ctH7dG78Id55',   // $299
    silo_team: 'https://buy.stripe.com/14AdRb9hv2Xq64E4yz',       // $799
    silo_pro: 'https://buy.stripe.com/00w14pgJXbtW64E1mn',        // $2,999
};

/**
 * Trigger Stripe Checkout
 * @param {string} priceId - The Stripe Price ID (e.g., price_12345)
 * @param {string} successUrl - Optional custom success URL
 */
async function checkout(priceId, successUrl) {
    if (!priceId) {
        console.error("Price ID is required for checkout.");
        return;
    }

    try {
        const { error } = await stripe.redirectToCheckout({
            lineItems: [{ price: priceId, quantity: 1 }],
            mode: 'payment',
            successUrl: successUrl || window.location.origin + '/success.html',
            cancelUrl: window.location.origin + '/cancel.html',
        });

        if (error) {
            console.error("Stripe Checkout Error:", error);
            alert("Payment failed: " + error.message);
        }
    } catch (err) {
        console.error("Payment Error:", err);
        alert("An unexpected error occurred.");
    }
}

/**
 * Redirect to Stripe Payment Link
 * This is the preferred method - uses Stripe's hosted payment page
 * @param {string} product - Product key from STRIPE_LINKS
 */
function buyProduct(product) {
    const link = STRIPE_LINKS[product];
    if (link && link !== 'PLACEHOLDER_CREATE_IN_STRIPE') {
        window.location.href = link;
    } else {
        console.error('Payment link not configured for:', product);
        alert('Payment not configured. Please contact admin@autominds.org');
    }
}

// Example usage:
// document.getElementById('checkout-button').addEventListener('click', () => {
//     checkout('price_H5ggYnDqa921');
// });
// Or use Payment Links directly:
// buyProduct('consultation');
