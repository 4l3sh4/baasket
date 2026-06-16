namespace Baasket.LogisticsV2;

/// <summary>
/// Subject in the Observer pattern for a single checkout lifecycle.
/// Mirrors the existing Baasket domain (buyer, payment reference, totals, optional offer)
/// without coupling to the legacy Python <c>logistics.py</c> module.
/// </summary>
public sealed class CheckoutSession : ISubject
{
    private readonly List<IObserver> _observers = [];

    public CheckoutSession(
        Guid sessionId,
        int buyerId,
        string buyerName,
        string buyerEmail,
        string paymentMethod,
        decimal subtotal,
        decimal fee,
        decimal total,
        string paymentReference,
        int? offerId = null,
        int? orderId = null)
    {
        if (buyerId <= 0)
            throw new ArgumentOutOfRangeException(nameof(buyerId));

        SessionId = sessionId;
        BuyerId = buyerId;
        BuyerName = buyerName ?? throw new ArgumentNullException(nameof(buyerName));
        BuyerEmail = buyerEmail ?? throw new ArgumentNullException(nameof(buyerEmail));
        PaymentMethod = paymentMethod ?? throw new ArgumentNullException(nameof(paymentMethod));
        Subtotal = subtotal;
        Fee = fee;
        Total = total;
        PaymentReference = paymentReference ?? throw new ArgumentNullException(nameof(paymentReference));
        OfferId = offerId;
        OrderId = orderId;
        State = CheckoutSessionState.CheckoutStarted;
        CreatedAtUtc = DateTime.UtcNow;
    }

    public Guid SessionId { get; }
    public int BuyerId { get; }
    public string BuyerName { get; }
    public string BuyerEmail { get; }
    public string PaymentMethod { get; }
    public decimal Subtotal { get; }
    public decimal Fee { get; }
    public decimal Total { get; }
    public string PaymentReference { get; }
    public int? OfferId { get; }
    public int? OrderId { get; private set; }
    public CheckoutSessionState State { get; private set; }
    public DateTime CreatedAtUtc { get; }
    public DateTime? PaymentConfirmedAtUtc { get; private set; }
    public DateTime? TrackingUpdatedAtUtc { get; private set; }
    public CheckoutReceipt? Receipt { get; private set; }

    public string StatusDisplay => CheckoutSessionStateDisplay.Display(State);

    public void Attach(IObserver observer)
    {
        ArgumentNullException.ThrowIfNull(observer);

        if (!_observers.Contains(observer))
            _observers.Add(observer);
    }

    public void Detach(IObserver observer)
    {
        ArgumentNullException.ThrowIfNull(observer);
        _observers.Remove(observer);
    }

    public void Notify(CheckoutSessionState previousState)
    {
        // Snapshot so observers can detach safely during notification.
        foreach (var observer in _observers.ToArray())
            observer.Update(this, previousState);
    }

    /// <summary>
    /// Transitions from <see cref="CheckoutSessionState.CheckoutStarted"/> to
    /// <see cref="CheckoutSessionState.PaymentConfirmed"/> and notifies observers.
    /// </summary>
    public void ConfirmPayment(int? orderId = null)
    {
        if (State != CheckoutSessionState.CheckoutStarted)
            throw new InvalidOperationException(
                $"Payment can only be confirmed from {CheckoutSessionState.CheckoutStarted}. Current state: {State}.");

        var previousState = State;
        State = CheckoutSessionState.PaymentConfirmed;
        PaymentConfirmedAtUtc = DateTime.UtcNow;

        if (orderId.HasValue)
            OrderId = orderId;

        Notify(previousState);
    }

    /// <summary>
    /// Called by <see cref="ReceiptGeneratorObserver"/> after payment confirmation.
    /// </summary>
    public void RecordReceipt(CheckoutReceipt receipt)
    {
        ArgumentNullException.ThrowIfNull(receipt);

        if (State != CheckoutSessionState.PaymentConfirmed)
            throw new InvalidOperationException("Receipt can only be recorded after payment is confirmed.");

        if (Receipt is not null)
            throw new InvalidOperationException("Receipt has already been generated for this session.");

        Receipt = receipt;
    }

    /// <summary>
    /// Advances tracking one step forward (Packed → Shipped → Delivered).
    /// Called by <see cref="AutomatedTrackingObserver"/> timers.
    /// </summary>
    public void AdvanceTo(CheckoutSessionState nextState)
    {
        if (!IsValidForwardTransition(State, nextState))
            throw new InvalidOperationException(
                $"Invalid transition: {State} → {nextState}.");

        var previousState = State;
        State = nextState;
        TrackingUpdatedAtUtc = DateTime.UtcNow;
        Notify(previousState);
    }

    private static bool IsValidForwardTransition(
        CheckoutSessionState current,
        CheckoutSessionState next)
    {
        return (current, next) switch
        {
            (CheckoutSessionState.PaymentConfirmed, CheckoutSessionState.Packed) => true,
            (CheckoutSessionState.Packed, CheckoutSessionState.Shipped) => true,
            (CheckoutSessionState.Shipped, CheckoutSessionState.Delivered) => true,
            _ => false,
        };
    }
}
