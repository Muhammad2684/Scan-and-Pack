const orderIdInput = document.getElementById('orderIdInput');
const orderDetailsDiv = document.getElementById('orderDetails');
const orderNameSpan = document.getElementById('orderName');
const shopifyOrderIdSpan = document.getElementById('shopifyOrderId');
const fulfillmentStatusSpan = document.getElementById('fulfillmentStatus');
const itemList = document.getElementById('itemList');
const statusMessageDiv = document.getElementById('statusMessage');
const markPackedBtn = document.getElementById('markPackedBtn');
const packedOrdersList = document.getElementById('packedOrdersList');
const packedTotalSpan = document.getElementById('packedTotal');

// Modal logic
const imageModal = document.getElementById("imageModal");
const modalImage = document.getElementById("modalImage");
const modalClose = document.querySelector(".image-modal .close");

modalClose.onclick = () => {
    imageModal.style.display = "none";
};

window.onclick = function (event) {
    if (event.target == imageModal) {
        imageModal.style.display = "none";
    }
};

let packedOrders = [];
let currentOrder = null;
let itemCounters = {};

orderIdInput.addEventListener('keypress', function (event) {
    if (event.key === 'Enter') {
        fetchOrder();
    }
});

function showMessage(message, type = 'info') {
    statusMessageDiv.textContent = message;
    statusMessageDiv.className = `status-message ${type}`;
    statusMessageDiv.style.display = 'block';
}

function clearMessage() {
    statusMessageDiv.textContent = '';
    statusMessageDiv.style.display = 'none';
}

async function fetchOrder() {
    const orderIdentifier = orderIdInput.value.trim();
    if (!orderIdentifier) {
        showMessage("Please scan or enter an Order ID/Number.", "error");
        return;
    }

    clearMessage();
    showMessage("Loading order...", "info");
    orderDetailsDiv.style.display = 'none';
    markPackedBtn.disabled = true;
    itemList.innerHTML = '';

    try {
        const response = await fetch(`/api/get_order/${orderIdentifier}`);
        const data = await response.json();

        if (!response.ok) {
            throw new Error(data.error || 'Failed to fetch order');
        }

        currentOrder = data;

        // ✅ Only check the "Packed" tag
        const tags = (data.tags || '').toLowerCase().split(',').map(t => t.trim());
        if (tags.some(tag => tag.startsWith('packed'))) {
            showMessage(`Order ${data.order_name} is already tagged as Packed.`, "info");
            return;
        }

        itemCounters = {};

        orderNameSpan.textContent = currentOrder.order_name;
        shopifyOrderIdSpan.textContent = currentOrder.order_id;
        fulfillmentStatusSpan.textContent = "N/A";

         currentOrder.line_items.forEach(item => {
            const qty = item.quantity || 1;
            itemCounters[item.variant_id] = 0;

            const li = document.createElement('li');
            li.dataset.variantId = item.variant_id;

            const imageHtml = item.product_image
                ? `<img src="${item.product_image}" alt="${item.title}" style="width: 70px; height: auto; margin-right: 10px; cursor: zoom-in; border-radius: 13px;" onclick="openImageModal('${item.product_image}')">`
                : '';

            li.innerHTML = `
                <div style="display: flex; align-items: center; gap: 10px;">
                    ${imageHtml}
                    <div>
                        <span>${item.title} (SKU: ${item.sku || 'N/A'})</span><br>
                        <span>Size: ${item.size || 'N/A'}</span>
                        <div style="display: flex; align-items: center;">
                            <span class="item-quantity">Packed: <span id="packed-${item.variant_id}">0</span> / ${qty}</span>
                            <div class="counter-controls">
                                <button onclick="decrementQuantity('${item.variant_id}')">-</button>
                                <button onclick="incrementQuantity('${item.variant_id}')">+</button>
                            </div>
                        </div>
                    </div>
                </div>
            `;

            // MODIFICATION START
            // Check if available_quantity is 0 or less
            if (item.quantity > item.available_quantity) {
                li.style.backgroundColor = 'rgba(255, 0, 0, 0.39)'; 
                li.title = `Warning: Not enough stock! Ordered ${item.quantity}, but only ${item.available_quantity ?? 0} available.`;
            }
            // MODIFICATION END
            

            itemList.appendChild(li);
        });

        orderDetailsDiv.style.display = 'block';
        checkPackingCompletion();
        clearMessage();

    } catch (error) {
        showMessage(`Error: ${error.message}`, "error");
        console.error("Fetch order error:", error);
    } finally {
        orderIdInput.value = '';
        orderIdInput.focus();
    }
}

function openImageModal(imageUrl) {
    modalImage.src = imageUrl;
    imageModal.style.display = "block";
}

function incrementQuantity(variantId) {
    const item = currentOrder.line_items.find(i => i.variant_id == variantId);
    if (!item) return;

    if (itemCounters[variantId] < item.quantity) {
        itemCounters[variantId]++;
        updateItemDisplay(variantId);
        checkPackingCompletion();
    } else {
        showMessage(`Already packed maximum quantity for ${item.title}.`, "info");
    }
}

function decrementQuantity(variantId) {
    const item = currentOrder.line_items.find(i => i.variant_id == variantId);
    if (!item) return;

    if (itemCounters[variantId] > 0) {
        itemCounters[variantId]--;
        updateItemDisplay(variantId);
        checkPackingCompletion();
    } else {
        showMessage(`Quantity for ${item.title} is already zero.`, "info");
    }
}

function updateItemDisplay(variantId) {
    const packedCountSpan = document.getElementById(`packed-${variantId}`);
    if (packedCountSpan) {
        packedCountSpan.textContent = itemCounters[variantId];
        const listItem = packedCountSpan.closest('li');
        const item = currentOrder.line_items.find(i => i.variant_id == variantId);

        if (itemCounters[variantId] === item.quantity) {
            listItem.classList.add('packed');
        } else {
            listItem.classList.remove('packed');
        }
    }
}

function checkPackingCompletion() {
    let allItemsPacked = true;
    currentOrder.line_items.forEach(item => {
        if (item.quantity > 0 && itemCounters[item.variant_id] !== item.quantity) {
            allItemsPacked = false;
        }
    });

    markPackedBtn.disabled = !allItemsPacked;
    if (allItemsPacked) {
        showMessage("All items are packed! Ready to tag order as Packed.", "success");
    } else {
        clearMessage();
    }
}

async function markOrderAsPacked() {
    if (!currentOrder || markPackedBtn.disabled) return;

    clearMessage();
    showMessage("Marking order as Tagged in Shopify...", "info");
    markPackedBtn.disabled = true;

    try {
        const response = await fetch(`/api/fulfill_order/${currentOrder.order_id}`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' }
        });

        const data = await response.json();

        if (!response.ok) {
            showMessage(data.error || 'Failed to fulfill order', 'error');
            return;
        }

        showMessage(`Order ${currentOrder.order_name} successfully fulfilled!`, "success");
        addPackedOrder(currentOrder.order_name);
        clearOrder();

    } catch (error) {
        showMessage(`Error: ${error.message}`, "error");
        console.error("Fulfillment error:", error);
    } finally {
        orderIdInput.focus();
    }
}

function addPackedOrder(orderName) {
    packedOrders.push(orderName);
    updatePackedOrdersUI();
}

function updatePackedOrdersUI() {
    packedOrdersList.innerHTML = '';
    packedOrders.forEach((order, i) => {
        const li = document.createElement('li');
        li.textContent = `${i + 1}. ${order}`;
        packedOrdersList.appendChild(li);
    });
    packedTotalSpan.textContent = packedOrders.length;
}

function clearPackedOrders() {
    packedOrders = [];
    updatePackedOrdersUI();
}

function clearOrder() {
    currentOrder = null;
    itemCounters = {};
    orderDetailsDiv.style.display = 'none';
    orderIdInput.value = '';
    itemList.innerHTML = '';
    orderNameSpan.textContent = '';
    shopifyOrderIdSpan.textContent = '';
    fulfillmentStatusSpan.textContent = '';
    markPackedBtn.disabled = true;
    clearMessage();
    orderIdInput.focus();
}

window.onload = () => {
    orderIdInput.focus();
};
