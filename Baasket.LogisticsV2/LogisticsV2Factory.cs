namespace Baasket.LogisticsV2;

/// <summary>
/// Wires the standard LogisticsV2 observers onto a checkout session.
/// Equivalent to the legacy Python <c>build_logistics_subject()</c>.
/// </summary>
public static class LogisticsV2Factory
{
    public static (ReceiptGeneratorObserver ReceiptObserver, AutomatedTrackingObserver TrackingObserver)
        WireStandardObservers(CheckoutSession session, TimeSpan? trackingStepDelay = null)
    {
        var receiptObserver = new ReceiptGeneratorObserver();
        var trackingObserver = new AutomatedTrackingObserver(trackingStepDelay);

        session.Attach(receiptObserver);
        session.Attach(trackingObserver);

        return (receiptObserver, trackingObserver);
    }
}
