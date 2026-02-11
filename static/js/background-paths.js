
const canvas = document.getElementById('hero-canvas');
const ctx = canvas.getContext('2d');

let width, height;
let paths = [];

const config = {
    pathCount: 15, // Reduced for subtlety
    segmentCount: 8, // Number of points per path
    speed: 0.002,
    amplitude: 80, // Vertical waviness
    verticalSpread: 200, // How spread out vertically
};

class Path {
    constructor(y) {
        this.y = y;
        this.offset = Math.random() * Math.PI * 2;
        this.speed = config.speed * (0.8 + Math.random() * 0.4);
        this.color = `rgba(255, 255, 255, ${0.03 + Math.random() * 0.05})`; // Very faint white
    }

    draw(time) {
        ctx.beginPath();
        const segmentWidth = width / config.segmentCount;

        ctx.moveTo(0, this.y + Math.sin(time * this.speed + this.offset) * config.amplitude);

        for (let i = 1; i <= config.segmentCount; i++) {
            const x = i * segmentWidth;
            const wave = Math.sin(time * this.speed + this.offset + i * 0.5) * config.amplitude;
            const y = this.y + wave;

            // Bezier curve for smoothness
            const prevX = (i - 1) * segmentWidth;
            const prevWave = Math.sin(time * this.speed + this.offset + (i - 1) * 0.5) * config.amplitude;
            const prevY = this.y + prevWave;

            const cpX = (prevX + x) / 2;
            ctx.quadraticCurveTo(cpX, prevY, x, y);
        }

        ctx.strokeStyle = this.color;
        ctx.lineWidth = 1.5;
        ctx.stroke();
    }
}

function init() {
    resize();
    createPaths();
    animate();
}

function resize() {
    width = canvas.width = window.innerWidth;
    height = canvas.height = window.innerHeight;
}

function createPaths() {
    paths = [];
    const centerY = height / 2;
    for (let i = 0; i < config.pathCount; i++) {
        // Distribute paths around the center
        const y = centerY - (config.verticalSpread / 2) + Math.random() * config.verticalSpread;
        paths.push(new Path(y));
    }
}

function animate(time = 0) {
    ctx.clearRect(0, 0, width, height);

    // Check for light mode to adjust color
    const isLightMode = document.body.classList.contains('light-mode');

    paths.forEach(path => {
        // Adjust color based on mode dynamically
        if (isLightMode) {
            // Darker lines for light mode
            path.color = path.color.replace('255, 255, 255', '0, 0, 0').replace('0.03', '0.05');
        } else {
            // White lines for dark mode (reset if needed, but simple replacement works for now)
            if (path.color.includes('0, 0, 0')) {
                path.color = path.color.replace('0, 0, 0', '255, 255, 255');
            }
        }
        path.draw(time);
    });

    requestAnimationFrame(animate);
}

window.addEventListener('resize', () => {
    resize();
    createPaths();
});

init();
